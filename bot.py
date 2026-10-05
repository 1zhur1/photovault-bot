"""Точка входа бота PhotoVault.

Запуск: python bot.py
Конфигурация берётся из .env (см. .env.example).
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from photovault.config import BOT_TOKEN
from photovault.db import init_db
from photovault.handlers import router
from photovault.middleware import Access


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise SystemExit(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
        )

    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(Access())
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="folders", description="Мои съёмки"),
        BotCommand(command="search", description="Поиск по папкам"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="cancel", description="Отменить действие"),
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())