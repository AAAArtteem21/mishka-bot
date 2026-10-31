from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from aiogram.types import ErrorEvent

import asyncio
import logging
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.services.answer_service import NO_ANSWER_TEXT, build_answer, format_answer
from app.services.search_service import search
from app.services.llm_client import GroqClient, LLMError
from app.services.scope_service import tag_chunks
from app.repositories.documents import ChunkData, DocumentRepository
from app.services.chunking import split_into_chunks
from app.services.extraction_service import ExtractionError, extract_text
from app.bot.states import UploadStates
from app.config import Settings
from app.db.models import SourceType, Chunk, Document
from app.repositories.users import UserRepository
from app.services.document_service import save_file, sha256_of, validate_file
from app.services.embedding_service import EmbeddingService

router = Router()

SCOPE_CHOICES = {
    "3": "Весь ліс",
    "2": "Частина лісу",
    "1": "Одна рукавичка",
    "0": "Це не порада",
}

START_TEXT = (
    "Привіт! Я Мишка-шкряботушка 🐭\n"
    "Надсилай мені документи (PDF, DOCX або TXT), а потім став запитання "
    "звичайним повідомленням — я пошукаю відповідь у всіх документах "
    "і назву джерело."
)

HELP_TEXT = (
    "Як мною користуватися:\n"
    "• Надішли файл PDF, DOCX або TXT (до 20 МБ). "
    "Уперше я спитаю твоє справжнє ім'я.\n"
    "• Напиши запитання звичайним текстом — я відповім українською "
    "і вкажу, з якого документа взято пораду.\n"
    "• Якщо відповіді в документах немає, я чесно про це скажу.\n\n"
    "Скановані PDF без текстового шару я поки не читаю."
)

ASK_NAME_TEXT = (
    "Ти в мене вперше 🐭 Як тебе звати по-справжньому? "
    "Я запам'ятаю ім'я й підписуватиму ним твої документи."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def store_document(
    bot: Bot,
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embeddings: EmbeddingService,
    llm: GroqClient,
    *,
    file_id: str,
    file_name: str,
    telegram_id: int,
    real_name: str | None = None,
) -> None:
    buffer = BytesIO()
    await bot.download(file_id, destination=buffer)
    data = buffer.getvalue()
    sha256 = sha256_of(data)

    async with session_factory() as session:
        users = UserRepository(session)
        documents = DocumentRepository(session)

        user = await users.get_by_telegram_id(telegram_id)
        if user is None:
            user = await users.create(telegram_id, real_name)
            await session.commit()

        existing = await documents.get_by_sha256(sha256)
        if existing:
            await message.answer(f"Документ «{existing.title}» вже є в базі.")
            return

        path = save_file(data, sha256, file_name, settings.data_dir)
        try:
            text = await asyncio.to_thread(extract_text, path)
        except ExtractionError as exc:
            Path(path).unlink(missing_ok=True)
            await message.answer(exc.user_message)
            return

        await message.answer("Читаю документ, це може тривати хвилину…")
        chunks = split_into_chunks(text)
        vectors = await embeddings.embed(chunks)
        try:
            tags = await tag_chunks(llm, file_name, chunks)
        except LLMError:
            logging.getLogger(__name__).warning("Groq недоступний", exc_info=True)
            Path(path).unlink(missing_ok=True)
            await message.answer(
                "Зараз не вдалося опрацювати документ. Спробуй надіслати його трохи пізніше."
            )
            return

        try:
            document = await documents.create(
                title=file_name,
                file_path=path,
                sha256=sha256,
                source_type=SourceType.USER,
                uploaded_by=user.id,
            )
            await documents.add_chunks(
                document.id,
                [
                    ChunkData(
                        text=c,
                        scope_level=t.level,
                        scope_label=t.label,
                        needs_clarification=t.needs_clarification,
                        embedding=v,
                    )
                    for c, v, t in zip(chunks, vectors, tags, strict=True)
                ],
            )
            document_id = document.id
            await session.commit()
        except IntegrityError:
            await session.rollback()
            await message.answer("Цей документ щойно додали, тож вдруге його не зберігаю.")
            return

        unclear = (
            await session.execute(
                select(Chunk.id, Chunk.text)
                .where(
                    Chunk.document_id == document_id,
                    Chunk.needs_clarification.is_(True),
                )
                .order_by(Chunk.position)
            )
        ).all()

        advice_count = sum(1 for t in tags if t.level is not None) + len(unclear)
        await message.answer(
            f"Документ «{file_name}» збережено й він доступний для пошуку.\n"
            f"Знайшла порад: {advice_count} із {len(chunks)} фрагментів."
        )
        for chunk_id, chunk_text in unclear:
            await message.answer(
                f"Для кого ця порада?\n\n«{chunk_text}»",
                reply_markup=scope_keyboard(chunk_id),
            )


@router.message(F.document)
async def handle_document(
    message: Message,
    bot: Bot,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embeddings: EmbeddingService,
    llm: GroqClient,
) -> None:
    doc = message.document
    error = validate_file(doc.file_name, doc.file_size, settings.max_file_size_mb)
    if error:
        await message.answer(error)
        return

    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(message.from_user.id)

    if user is None:
        await state.set_state(UploadStates.waiting_name)
        await state.update_data(file_id=doc.file_id, file_name=doc.file_name)
        await message.answer(ASK_NAME_TEXT)
        return

    await store_document(
        bot,
        message,
        session_factory,
        settings,
        embeddings,
        llm,
        file_id=doc.file_id,
        file_name=doc.file_name,
        telegram_id=message.from_user.id,
    )


@router.message(UploadStates.waiting_name, F.text)
async def handle_name(
    message: Message,
    bot: Bot,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embeddings: EmbeddingService,
    llm: GroqClient,
) -> None:
    name = message.text.strip()
    if not name or len(name) > 255 or name.startswith("/"):
        await message.answer("Напиши, будь ласка, своє ім'я одним коротким повідомленням.")
        return

    data = await state.get_data()
    await state.clear()
    await store_document(
        bot,
        message,
        session_factory,
        settings,
        embeddings,
        llm,
        file_id=data["file_id"],
        file_name=data["file_name"],
        telegram_id=message.from_user.id,
        real_name=name,
    )


def scope_keyboard(chunk_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=title, callback_data=f"scope:{chunk_id}:{code}")
        for code, title in SCOPE_CHOICES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons])


@router.callback_query(F.data.startswish("scope:"))
async def hande_scope_answer(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _, chunk_id_raw, code = callback.data.split(":")
    if code not in SCOPE_CHOICES:
        await callback.answer()
        return

    async with session_factory() as session:
        chunk = await session.get(Chunk, int(chunk_id_raw))
        if chunk is None:
            await callback.answer("Фрагмент не знайдено.", show_alert=True)
            return
        uploader = chunk.document.uploader
        if uploader is None or uploader.telegram_id != callback.from_user.id:
            await callback.answer("Це не твій документ.", show_alert=True)
            return
        if not chunk.needs_clarification:
            await callback.answer("Вже відповіли.")
            return

        chunk.scope_level = int(code) or None
        chunk.needs_clarification = False
        await session.commit()

    await callback.message.edit_text(
        f"{callback.message.text}\n\n✅ {SCOPE_CHOICES[code]}"
    )
    await callback.answer()


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_question(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    embeddings: EmbeddingService,
    llm: GroqClient,
) -> None:
    question = message.text.strip()
    if len(question) > 500:
        await message.answer("Запитаня задовге. Спробуй сформулювати коротше 500 символів.")
        return 

    await bot.send_chat_action(message.chat.id, "typing")
    async with session_factory() as session:
        hits = await search(session, embeddings, question)
    if not hits:
        await message.answer(NO_ANSWER_TEXT)
        return

    try:
        answer = await build_answer(llm, question, hits)
    except LLMError:
        logging.getLogger(__name__).warning("Groq недоступний", exc_info=True)
        await message.answer("Зараз не вдалося підготувати відповідь. Спробуй трохи пізніше.")
        return
    await message.answer(format_answer(answer))

@router.error()
async def on_error(event: ErrorEvent) -> bool:
    logging.getLogger(__name__).error(
        "Помилка обробки оновлення", exc_info=event.exception
    )
    update = event.update
    message = update.message or (update.callback_query and update.callback_query.message)
    if message:
        await message.answer("Щось пішло не так. Спробуй ще раз трохи пізніше.")
    return True