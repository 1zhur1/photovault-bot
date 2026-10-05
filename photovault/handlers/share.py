"""Ссылки для клиентов: генерация, показ и отключение."""

import secrets

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from ..db import load_tree, set_share_token
from ..keyboards import btn, kb, safe_edit
from ..utils import esc

from .folders import folder_card

router = Router()


async def show_share(cb: CallbackQuery, bot: Bot, folder_id: int, token: str, name: str) -> None:
    me = await bot.me()
    link = f"https://t.me/{me.username}?start=s_{token}"
    text = (
        f"🔗 <b>Ссылка на «{esc(name)}»</b>\n\n{link}\n\n"
        "Кто откроет ссылку, получит от бота все файлы этой папки и её подпапок "
        "(без возможности что-либо менять). Ссылку можно в любой момент отключить или заменить.\n\n"
        "💡 Чтобы клиент получил только готовые фото, включите ссылку не на всей съёмке, "
        "а на подпапке «Обработанные»."
    )
    markup = kb([
        [btn("🔄 Новая ссылка", f"shn:{folder_id}"), btn("🚫 Отключить", f"shx:{folder_id}")],
        [btn("⬅️ К папке", f"f:{folder_id}")],
    ])
    await safe_edit(cb, text, markup, no_preview=True)


@router.callback_query(F.data.startswith("sh:"))
async def cb_share(cb: CallbackQuery, bot: Bot):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    f = tree.by_id.get(folder_id)
    if not f:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    token = f["share_token"]
    if not token:
        token = secrets.token_urlsafe(9)
        await set_share_token(cb.from_user.id, folder_id, token)
    await cb.answer()
    await show_share(cb, bot, folder_id, token, tree.path(folder_id))


@router.callback_query(F.data.startswith("shn:"))
async def cb_share_new(cb: CallbackQuery, bot: Bot):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    token = secrets.token_urlsafe(9)
    await set_share_token(cb.from_user.id, folder_id, token)
    await cb.answer("Создана новая ссылка, старая больше не работает")
    await show_share(cb, bot, folder_id, token, tree.path(folder_id))


@router.callback_query(F.data.startswith("shx:"))
async def cb_share_off(cb: CallbackQuery):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    await set_share_token(cb.from_user.id, folder_id, None)
    await cb.answer("Ссылка отключена")
    text, markup = await folder_card(cb.from_user.id, folder_id)
    await safe_edit(cb, text, markup)