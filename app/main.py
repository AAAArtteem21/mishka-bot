import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.config import get_settings
from app.db.session import make_engine, make_session_factory
from app.services.embedding_service import EmbeddingService
from app.services.llm_client import GroqClient


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY не задано в .env")

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    embeddings = EmbeddingService(cache_dir=f"{settings.data_dir}/models")
    llm = GroqClient(settings.groq_api_key, settings.groq_model)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(
        session_factory=session_factory,
        settings=settings,
        embeddings=embeddings,
        llm=llm,
    )
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await llm.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())