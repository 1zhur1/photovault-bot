"""Основные команды и главное меню: /start, /menu, /cancel, /folders, /stats, /search."""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..db import get_folder_by_token, load_tree
from ..keyboards import main_menu_kb, safe_edit
from ..sending import run_download
from ..states import Search
from ..texts import MENU_TEXT
from ..utils import esc

from .folders import folders_page
from .stats import stats_text

router = Router()


@router.message(CommandStart(deep_link=True))
async def cmd_start_link(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    arg = command.args or ""
    if not arg.startswith("s_"):
        await cmd_start(message, state)
        return
    await state.clear()
    folder = await get_folder_by_token(arg[2:])
    if not folder:
        await message.answer("Ссылка недействительна или была отключена.")
        return
    tree = await load_tree(folder["user_id"])
    total = tree.total(folder["id"])
    if total == 0:
        await message.answer(f"Папка «{esc(folder['name'])}» пока пуста. Загляните позже.")
        return
    await message.answer(
        f"📸 С вами поделились папкой <b>{esc(folder['name'])}</b>. Файлов: {total}.\nОтправляю…"
    )
    await run_download(bot, message.chat.id, message.from_user.id, tree, folder["id"])


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=main_menu_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu_kb())


@router.message(Command("folders"))
async def cmd_folders(message: Message, state: FSMContext):
    await state.clear()
    text, markup = await folders_page(message.from_user.id, 0)
    await message.answer(text, reply_markup=markup)


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(await stats_text(message.from_user.id), reply_markup=main_menu_kb())


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    await state.set_state(Search.query)
    await message.answer("Что искать? Введите часть названия папки или заметки.\nОтмена — /cancel")


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await safe_edit(cb, MENU_TEXT, main_menu_kb())