"""Кнопки, клавиатуры и безопасное редактирование сообщений."""

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def safe_edit(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None,
                    no_preview: bool = False) -> None:
    opts = LinkPreviewOptions(is_disabled=True) if no_preview else None
    try:
        await cb.message.edit_text(text, reply_markup=markup, link_preview_options=opts)
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return
        await cb.message.answer(text, reply_markup=markup, link_preview_options=opts)


def main_menu_kb() -> InlineKeyboardMarkup:
    return kb([
        [btn("📁 Мои съёмки", "fl:0")],
        [btn("➕ Новая съёмка", "new")],
        [btn("🔎 Поиск", "search"), btn("📊 Статистика", "stats")],
    ])