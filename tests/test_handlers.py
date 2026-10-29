from unittest.mock import AsyncMock

from app.bot.handlers import HELP_TEXT, START_TEXT, cmd_help, cmd_start


async def test_start_replies_with_greeting():
    message = AsyncMock()
    await cmd_start(message)
    message.answer.assert_awaited_once_with(START_TEXT)


async def test_help_replies_with_instructions():
    message = AsyncMock()
    await cmd_help(message)
    message.answer.assert_awaited_once_with(HELP_TEXT)
