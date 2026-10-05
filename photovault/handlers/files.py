"""Загрузка файлов в папки, просмотр содержимого и «Скачать всё»."""

import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import VIEW_PAGE
from ..db import add_file, get_files, load_tree, undo_batch
from ..keyboards import btn, kb, safe_edit
from ..sending import downloading, run_download, send_rows
from ..states import Upload
from ..utils import esc

router = Router()

# user_id -> {"new": int, "dup": int, "batch": int, "folder_id": int, "task": asyncio.Task}
pending: dict[int, dict] = {}


# ───────────────────────────── Загрузка ─────────────────────────────

@router.callback_query(F.data.startswith("up:"))
async def cb_upload(cb: CallbackQuery, state: FSMContext):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    await state.set_state(Upload.active)
    await state.update_data(folder_id=folder_id)
    await cb.answer()
    await safe_edit(
        cb,
        f"📤 Режим загрузки в папку <b>{esc(tree.path(folder_id))}</b>.\n\n"
        "Присылайте фото, видео и файлы — можно выбирать сразу много. "
        "Когда закончите, нажмите «Готово».\n\n"
        "💡 Отправляйте как <b>файл</b>, если важно оригинальное качество.",
        kb([[btn("✅ Готово", f"f:{folder_id}")]]),
    )


def extract_media(m: Message):
    """Возвращает (kind, file_id, unique_id, file_name, size) или None."""
    if m.photo:
        p = m.photo[-1]
        return "photo", p.file_id, p.file_unique_id, None, p.file_size
    if m.video:
        v = m.video
        return "video", v.file_id, v.file_unique_id, v.file_name, v.file_size
    if m.document:
        d = m.document
        return "document", d.file_id, d.file_unique_id, d.file_name, d.file_size
    return None


async def flush_summary(bot: Bot, chat_id: int, user_id: int) -> None:
    """Через 1.5 с после последнего файла отправляет одну сводку вместо сообщения на каждый файл."""
    await asyncio.sleep(1.5)
    st = pending.pop(user_id, None)
    if not st:
        return
    text = f"✅ Сохранено: {st['new']}"
    if st["dup"]:
        text += f"\n♻️ Уже были в папке (пропущено): {st['dup']}"
    text += "\n\nПродолжайте присылать или нажмите «Готово»."
    rows = [[btn("✅ Готово", f"f:{st['folder_id']}")]]
    if st["new"]:
        rows.append([btn("↩️ Отменить эту загрузку", f"undo:{st['folder_id']}:{st['batch']}")])
    await bot.send_message(chat_id, text, reply_markup=kb(rows))


@router.message(Upload.active, F.photo | F.video | F.document)
async def upload_media(message: Message, state: FSMContext, bot: Bot):
    folder_id = (await state.get_data())["folder_id"]
    user_id = message.from_user.id
    media = extract_media(message)
    if media is None:
        return
    kind, file_id, unique_id, file_name, size = media

    st = pending.get(user_id)
    if st is None or st["folder_id"] != folder_id:
        st = {"new": 0, "dup": 0, "batch": int(time.time() * 1000), "folder_id": folder_id, "task": None}
        pending[user_id] = st

    added = await add_file(folder_id, user_id, kind, file_id, unique_id, file_name, size, st["batch"])
    st["new" if added else "dup"] += 1
    if st["task"] and not st["task"].done():
        st["task"].cancel()
    st["task"] = asyncio.create_task(flush_summary(bot, message.chat.id, user_id))


@router.message(Upload.active)
async def upload_other(message: Message):
    await message.answer("В режиме загрузки я принимаю фото, видео и файлы. Для выхода — /cancel.")


@router.callback_query(F.data.startswith("undo:"))
async def cb_undo(cb: CallbackQuery):
    _, fid, batch = cb.data.split(":")
    n = await undo_batch(cb.from_user.id, int(fid), int(batch))
    await cb.answer(f"Удалено файлов: {n}", show_alert=True)
    await safe_edit(
        cb,
        f"↩️ Загрузка отменена, удалено файлов: {n}.\nМожно присылать файлы заново или нажать «Готово».",
        kb([[btn("✅ Готово", f"f:{fid}")]]),
    )


# ───────────────────────────── Просмотр и «Скачать всё» ─────────────────────────────

@router.callback_query(F.data.startswith("v:"))
async def cb_view(cb: CallbackQuery, bot: Bot):
    _, fid, off = cb.data.split(":")
    folder_id, offset = int(fid), int(off)
    tree = await load_tree(cb.from_user.id)
    folder = tree.by_id.get(folder_id)
    if not folder:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    total = tree.own.get(folder_id, 0)
    if total == 0:
        hint = " Загляните в подпапки." if tree.children.get(folder_id) else ""
        await cb.answer("В этой папке нет файлов." + hint, show_alert=True)
        return
    rows = await get_files(folder_id, offset, VIEW_PAGE)
    if not rows:
        await cb.answer("Это конец списка", show_alert=True)
        return
    await cb.answer()

    chat_id = cb.message.chat.id
    await send_rows(bot, chat_id, rows)

    shown = offset + len(rows)
    buttons = []
    if shown < total:
        buttons.append([btn(f"➡️ Ещё ({total - shown})", f"v:{folder_id}:{shown}")])
    buttons.append([btn("⬅️ В папку", f"f:{folder_id}")])
    await bot.send_message(
        chat_id,
        f"📁 <b>{esc(tree.path(folder_id))}</b>: показано {shown} из {total}",
        reply_markup=kb(buttons),
    )


@router.callback_query(F.data.startswith("da:"))
async def cb_download_all(cb: CallbackQuery, bot: Bot):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    if tree.total(folder_id) == 0:
        await cb.answer("В папке нет файлов", show_alert=True)
        return
    if cb.from_user.id in downloading:
        await cb.answer("Отправка уже идёт, подождите", show_alert=True)
        return
    await cb.answer()
    await run_download(bot, cb.message.chat.id, cb.from_user.id, tree, folder_id)