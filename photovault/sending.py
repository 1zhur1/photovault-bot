"""Отправка файлов клиентам и владельцу: альбомы, анти-флуд, «Скачать всё»."""

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo

from .config import SEND_DELAY, log
from .db import get_files
from .tree import Tree
from .utils import esc


def to_input_media(row):
    if row["kind"] == "photo":
        return InputMediaPhoto(media=row["file_id"])
    if row["kind"] == "video":
        return InputMediaVideo(media=row["file_id"])
    return InputMediaDocument(media=row["file_id"])


async def with_retry(func, *args, **kwargs):
    """Повторяет вызов при превышении лимита Telegram (flood control)."""
    for _ in range(5):
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
    return await func(*args, **kwargs)


async def send_one(bot: Bot, chat_id: int, r) -> None:
    if r["kind"] == "photo":
        await with_retry(bot.send_photo, chat_id, r["file_id"])
    elif r["kind"] == "video":
        await with_retry(bot.send_video, chat_id, r["file_id"])
    else:
        await with_retry(bot.send_document, chat_id, r["file_id"])


async def send_group(bot: Bot, chat_id: int, group: list) -> int:
    """Отправляет группу файлов (альбомом, если их больше одного). Возвращает число отправленных."""
    if not group:
        return 0
    if len(group) > 1:
        try:
            await with_retry(bot.send_media_group, chat_id, [to_input_media(r) for r in group])
            await asyncio.sleep(SEND_DELAY)
            return len(group)
        except TelegramBadRequest:
            log.warning("Альбом не отправился, пробую по одному файлу")
    ok = 0
    for r in group:
        try:
            await send_one(bot, chat_id, r)
            ok += 1
        except TelegramBadRequest as e:
            log.warning("Файл пропущен: %s", e)
        await asyncio.sleep(SEND_DELAY)
    return ok


async def send_rows(bot: Bot, chat_id: int, rows: list) -> int:
    # Telegram не позволяет смешивать документы с фото/видео в одном альбоме.
    ok = await send_group(bot, chat_id, [r for r in rows if r["kind"] in ("photo", "video")])
    ok += await send_group(bot, chat_id, [r for r in rows if r["kind"] == "document"])
    return ok


downloading: set[int] = set()


async def run_download(bot: Bot, chat_id: int, user_id: int, tree: Tree, root_id: int) -> None:
    """Отправляет все файлы папки и её подпапок. Один пользователь — одна отправка за раз."""
    if user_id in downloading:
        await bot.send_message(chat_id, "⏳ Предыдущая отправка ещё идёт. Дождитесь её завершения.")
        return
    downloading.add(user_id)
    try:
        await send_tree(bot, chat_id, tree, root_id)
    finally:
        downloading.discard(user_id)


async def send_tree(bot: Bot, chat_id: int, tree: Tree, root_id: int) -> None:
    order = tree.walk(root_id)
    total = sum(tree.own.get(f["id"], 0) for f, _ in order)
    status = await bot.send_message(chat_id, f"⏳ Отправляю файлы: 0 из {total}…")
    sent = failed = 0

    for folder, path in order:
        n = tree.own.get(folder["id"], 0)
        if not n:
            continue
        await with_retry(bot.send_message, chat_id, f"📂 <b>{esc(path)}</b> — {n}")
        offset = 0
        while offset < n:
            rows = await get_files(folder["id"], offset, 10)
            if not rows:
                break
            ok = await send_rows(bot, chat_id, rows)
            sent += ok
            failed += len(rows) - ok
            offset += len(rows)
            try:
                await status.edit_text(f"⏳ Отправляю файлы: {sent} из {total}…")
            except TelegramBadRequest:
                pass

    result = f"✅ Готово. Отправлено файлов: {sent} из {total}."
    if failed:
        result += f"\n⚠️ Не удалось отправить: {failed}."
    result += "\n\n💡 Чтобы сохранить всё в галерею: откройте чат, выделите файлы и нажмите «Сохранить»."
    try:
        await status.edit_text(result)
    except TelegramBadRequest:
        await bot.send_message(chat_id, result)