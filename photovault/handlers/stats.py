"""Статистика хранилища."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ..db import get_stats
from ..keyboards import btn, kb, safe_edit
from ..utils import human_size

router = Router()


async def stats_text(user_id: int) -> str:
    st = await get_stats(user_id)
    k = st["kinds"]
    photo, video, doc = k.get("photo", (0, 0)), k.get("video", (0, 0)), k.get("document", (0, 0))
    total_files = photo[0] + video[0] + doc[0]
    total_size = photo[1] + video[1] + doc[1]
    return (
        "📊 <b>Статистика</b>\n"
        f"Съёмок: {st['roots']}  ·  всего папок: {st['folders']}\n"
        f"📷 Фото: {photo[0]}  ({human_size(photo[1])})\n"
        f"🎬 Видео: {video[0]}  ({human_size(video[1])})\n"
        f"📄 Файлы: {doc[0]}  ({human_size(doc[1])})\n"
        f"━━━━━━━━\nВсего файлов: {total_files}  ·  {human_size(total_size)}\n"
        "<i>Размеры — по данным Telegram.</i>"
    )


@router.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await safe_edit(cb, await stats_text(cb.from_user.id), kb([[btn("🏠 Меню", "menu")]]))