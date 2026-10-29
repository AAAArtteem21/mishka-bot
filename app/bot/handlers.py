from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

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


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
