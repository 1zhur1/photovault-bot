"""«Хватающие всё» обработчики. Подключаются последними, чтобы не перехватывать события раньше других хендлеров."""

from aiogram import F, Router
from aiogram.types import Message

from ..keyboards import main_menu_kb

router = Router()


@router.message(F.photo | F.video | F.document)
async def media_outside_upload(message: Message):
    await message.answer(
        "Чтобы сохранить файл, сначала выберите папку: «Мои съёмки» → папка → «Загрузить».",
        reply_markup=main_menu_kb(),
    )


@router.message()
async def fallback(message: Message):
    await message.answer("Откройте меню: /menu", reply_markup=main_menu_kb())