"""
Точка входа: запускает всех ботов проекта из одной точки.

Сейчас встроен только Telegram-бот (пакет telegram/).
В будущем здесь появятся остальные платформы — VK, Messenger Max и др.
"""

import asyncio
import os
import sys

from telegram.bot import main as run_telegram_bot
from telegram.console_worker import RestartRequested


async def run_all():
    """Запускает всех ботов. Сейчас — только Telegram."""
    await run_telegram_bot()


if __name__ == '__main__':
    try:
        asyncio.run(run_all())
    except RestartRequested:
        print("Перезапуск ботов...")
        os.execl(
            sys.executable,
            sys.executable,
            os.path.abspath(__file__),
        )