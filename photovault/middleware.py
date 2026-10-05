"""Мидлварь ограничения доступа."""

from aiogram import BaseMiddleware

from .config import ALLOWED


class Access(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not ALLOWED:
            return await handler(event, data)
        user = data.get("event_from_user")
        if user is not None and user.id in ALLOWED:
            return await handler(event, data)
        msg = getattr(event, "message", None)
        if msg is not None and msg.text and msg.text.startswith("/start s_"):
            return await handler(event, data)  # клиент открыл ссылку на папку
        return None