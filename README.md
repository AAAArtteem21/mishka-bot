# Мишка-шкряботушка

Telegram-бот, який відповідає на запитання за документами (PDF, DOCX, TXT).

## Запуск

1. `cp .env.example .env` і впиши `BOT_TOKEN` (від @BotFather) та `GROQ_API_KEY`.
2. `docker compose up --build`

## Тести

    pip install -e ".[dev]"
    pytest
