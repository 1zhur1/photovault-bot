"""Папки и съёмки: карточка, список, создание, переименование, заметки, удаление, поиск."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from ..config import FOLDERS_PAGE, MAX_DEPTH, MAX_NAME_LEN, MAX_NOTE_LEN, PRESETS
from ..db import (
    count_by_kind,
    create_folder,
    delete_folders,
    load_tree,
    rename_folder,
    set_note,
)
from ..keyboards import btn, kb, safe_edit
from ..states import EditNote, NewFolder, RenameFolder, Search
from ..utils import clean_name, esc, short

router = Router()


# ───────────────────────────── Карточка папки и список ─────────────────────────────

async def folder_card(user_id: int, folder_id: int):
    tree = await load_tree(user_id)
    f = tree.by_id.get(folder_id)
    if not f:
        return None, None
    own = await count_by_kind(folder_id)
    kids = tree.children.get(folder_id, [])
    total = tree.total(folder_id)

    lines = [f"📁 <b>{esc(tree.path(folder_id))}</b>"]
    if f["note"]:
        lines.append(f"📝 {esc(f['note'])}")
    lines.append(f"📷 {own['photo']}  ·  🎬 {own['video']}  ·  📄 {own['document']}  (в этой папке)")
    if kids:
        lines.append(f"📦 Всего с подпапками: {total}")
    if f["share_token"]:
        lines.append("🔗 Доступ по ссылке включён")
    lines.append(f"Создана: {f['created_at'][:10]}")

    rows: list[list[InlineKeyboardButton]] = []
    for c in kids:
        rows.append([btn(f"📂 {short(c['name'])} ({tree.total(c['id'])})", f"f:{c['id']}")])
    rows.append([btn("📤 Загрузить", f"up:{folder_id}"), btn("👁 Смотреть", f"v:{folder_id}:0")])
    rows.append([btn(f"⬇️ Скачать всё ({total})", f"da:{folder_id}")])

    sub_row = []
    if tree.depth(folder_id) < MAX_DEPTH:
        sub_row.append(btn("➕ Подпапка", f"sub:{folder_id}"))
    if sub_row:
        rows.append(sub_row)
    child_names = {c["name"] for c in kids}
    if f["parent_id"] == 0 and not all(p in child_names for p in PRESETS):
        rows.append([btn("🧱 Исходники + Обработанные", f"preset:{folder_id}")])

    rows.append([btn("🔗 Поделиться", f"sh:{folder_id}"), btn("📝 Заметка", f"nt:{folder_id}")])
    rows.append([btn("✏️ Переименовать", f"rn:{folder_id}"), btn("🗑 Удалить", f"dl:{folder_id}")])
    back = "fl:0" if f["parent_id"] == 0 else f"f:{f['parent_id']}"
    rows.append([btn("⬅️ Назад", back)])
    return "\n".join(lines), kb(rows)


async def folders_page(user_id: int, page: int):
    tree = await load_tree(user_id)
    roots = sorted(tree.children.get(0, []), key=lambda f: -f["id"])
    if not roots:
        return "У вас пока нет съёмок. Создайте первую!", kb([[btn("➕ Новая съёмка", "new")]])

    pages = (len(roots) + FOLDERS_PAGE - 1) // FOLDERS_PAGE
    page = max(0, min(page, pages - 1))
    chunk = roots[page * FOLDERS_PAGE:(page + 1) * FOLDERS_PAGE]

    rows = [[btn(f"📁 {short(f['name'])} ({tree.total(f['id'])})", f"f:{f['id']}")] for f in chunk]
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"fl:{page - 1}"))
    if page < pages - 1:
        nav.append(btn("▶️", f"fl:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("➕ Новая съёмка", "new"), btn("🏠 Меню", "menu")])
    return f"📁 <b>Ваши съёмки</b> — стр. {page + 1}/{pages}, всего: {len(roots)}", kb(rows)


@router.callback_query(F.data.startswith("fl:"))
async def cb_folders(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    text, markup = await folders_page(cb.from_user.id, int(cb.data.split(":")[1]))
    await safe_edit(cb, text, markup)


@router.callback_query(F.data.startswith("f:"))
async def cb_folder(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    text, markup = await folder_card(cb.from_user.id, int(cb.data.split(":")[1]))
    if not text:
        await safe_edit(cb, "Папка не найдена.", kb([[btn("🏠 Меню", "menu")]]))
        return
    await safe_edit(cb, text, markup)


# ───────────────────────────── Создание / переименование ─────────────────────────────

@router.callback_query(F.data == "new")
async def cb_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NewFolder.name)
    await state.update_data(parent_id=0)
    await cb.answer()
    await cb.message.answer(
        f"Введите название съёмки (до {MAX_NAME_LEN} символов), например: «Свадьба Иван и Мария, 12.06».\n"
        "Отмена — /cancel"
    )


@router.callback_query(F.data.startswith("sub:"))
async def cb_sub(cb: CallbackQuery, state: FSMContext):
    parent_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if parent_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    if tree.depth(parent_id) >= MAX_DEPTH:
        await cb.answer(f"Максимальная вложенность — {MAX_DEPTH} уровня", show_alert=True)
        return
    await state.set_state(NewFolder.name)
    await state.update_data(parent_id=parent_id)
    await cb.answer()
    await cb.message.answer(
        f"Введите название подпапки внутри «{esc(tree.path(parent_id))}».\nОтмена — /cancel"
    )


@router.message(NewFolder.name, F.text)
async def new_folder_name(message: Message, state: FSMContext):
    name = clean_name(message.text)
    if not name or name.startswith("/"):
        await message.answer("Введите обычное название папки или /cancel.")
        return
    if len(name) > MAX_NAME_LEN:
        await message.answer(f"Слишком длинно, максимум {MAX_NAME_LEN} символов. Попробуйте короче.")
        return
    data = await state.get_data()
    parent_id = data.get("parent_id", 0)
    user_id = message.from_user.id
    folder_id = await create_folder(user_id, parent_id, name)
    if folder_id is None:
        await message.answer("Папка с таким названием здесь уже есть. Придумайте другое.")
        return
    await state.clear()

    if parent_id == 0:
        await message.answer(
            f"✅ Съёмка «{esc(name)}» создана.\nДобавить стандартные подпапки «Исходники» и «Обработанные»?",
            reply_markup=kb([
                [btn("🧱 Да, добавить", f"preset:{folder_id}")],
                [btn("Нет, открыть папку", f"f:{folder_id}")],
            ]),
        )
        return
    text, markup = await folder_card(user_id, folder_id)
    await message.answer("✅ Подпапка создана.\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("preset:"))
async def cb_preset(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    for name in PRESETS:
        await create_folder(cb.from_user.id, folder_id, name)  # существующие просто пропускаются
    await cb.answer("Подпапки добавлены")
    text, markup = await folder_card(cb.from_user.id, folder_id)
    await safe_edit(cb, text, markup)


@router.callback_query(F.data.startswith("rn:"))
async def cb_rename(cb: CallbackQuery, state: FSMContext):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    await state.set_state(RenameFolder.name)
    await state.update_data(folder_id=folder_id)
    await cb.answer()
    await cb.message.answer("Введите новое название папки.\nОтмена — /cancel")


@router.message(RenameFolder.name, F.text)
async def rename_folder_name(message: Message, state: FSMContext):
    name = clean_name(message.text)
    if not name or name.startswith("/"):
        await message.answer("Введите обычное название папки или /cancel.")
        return
    if len(name) > MAX_NAME_LEN:
        await message.answer(f"Слишком длинно, максимум {MAX_NAME_LEN} символов.")
        return
    folder_id = (await state.get_data())["folder_id"]
    if not await rename_folder(message.from_user.id, folder_id, name):
        await message.answer("Не получилось: папка с таким названием здесь уже есть. Введите другое.")
        return
    await state.clear()
    text, markup = await folder_card(message.from_user.id, folder_id)
    await message.answer("✅ Переименовано.\n\n" + text, reply_markup=markup)


# ───────────────────────────── Заметка ─────────────────────────────

@router.callback_query(F.data.startswith("nt:"))
async def cb_note(cb: CallbackQuery, state: FSMContext):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    await state.set_state(EditNote.text)
    await state.update_data(folder_id=folder_id)
    await cb.answer()
    await cb.message.answer(
        f"Введите заметку к папке (клиент, место, пожелания — до {MAX_NOTE_LEN} символов).\n"
        "Чтобы удалить заметку, отправьте «-». Отмена — /cancel"
    )


@router.message(EditNote.text, F.text)
async def note_text(message: Message, state: FSMContext):
    raw = message.text.strip()
    if raw.startswith("/"):
        await message.answer("Введите текст заметки, «-» или /cancel.")
        return
    if len(raw) > MAX_NOTE_LEN:
        await message.answer(f"Слишком длинно, максимум {MAX_NOTE_LEN} символов.")
        return
    folder_id = (await state.get_data())["folder_id"]
    await set_note(message.from_user.id, folder_id, None if raw == "-" else raw)
    await state.clear()
    text, markup = await folder_card(message.from_user.id, folder_id)
    await message.answer("✅ Заметка обновлена.\n\n" + text, reply_markup=markup)


# ───────────────────────────── Удаление ─────────────────────────────

@router.callback_query(F.data.startswith("dl:"))
async def cb_delete(cb: CallbackQuery):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    if folder_id not in tree.by_id:
        await cb.answer("Папка не найдена", show_alert=True)
        return
    await cb.answer()
    subs = len(tree.subtree_ids(folder_id)) - 1
    text = f"Удалить папку <b>{esc(tree.path(folder_id))}</b>"
    if subs:
        text += f", {subs} подпапок(и)"
    text += f" и все файлы внутри ({tree.total(folder_id)})?\nДействие необратимо."
    await safe_edit(
        cb,
        text,
        kb([[btn("🗑 Да, удалить", f"dly:{folder_id}"), btn("Отмена", f"f:{folder_id}")]]),
    )


@router.callback_query(F.data.startswith("dly:"))
async def cb_delete_yes(cb: CallbackQuery):
    folder_id = int(cb.data.split(":")[1])
    tree = await load_tree(cb.from_user.id)
    folder = tree.by_id.get(folder_id)
    if not folder:
        await cb.answer("Папка уже удалена", show_alert=True)
        return
    parent_id = folder["parent_id"]
    await delete_folders(cb.from_user.id, tree.subtree_ids(folder_id))
    await cb.answer("Папка удалена")
    if parent_id:
        text, markup = await folder_card(cb.from_user.id, parent_id)
    else:
        text, markup = await folders_page(cb.from_user.id, 0)
    await safe_edit(cb, text, markup)


# ───────────────────────────── Поиск ─────────────────────────────

@router.callback_query(F.data == "search")
async def cb_search(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Search.query)
    await cb.answer()
    await cb.message.answer("Что искать? Введите часть названия папки или заметки.\nОтмена — /cancel")


@router.message(Search.query, F.text)
async def search_query(message: Message, state: FSMContext):
    q = clean_name(message.text).lower()
    if not q or q.startswith("/"):
        await message.answer("Введите текст для поиска или /cancel.")
        return
    await state.clear()
    tree = await load_tree(message.from_user.id)
    found = []
    for fid, f in tree.by_id.items():
        path = tree.path(fid)
        if q in path.lower() or q in (f["note"] or "").lower():
            found.append((fid, path))
    found.sort(key=lambda x: -x[0])
    if not found:
        await message.answer("Ничего не найдено.", reply_markup=kb([[btn("🏠 Меню", "menu")]]))
        return
    rows = [[btn(f"📁 {short(p, 48)} ({tree.total(i)})", f"f:{i}")] for i, p in found[:20]]
    rows.append([btn("🏠 Меню", "menu")])
    extra = f" (показаны первые 20 из {len(found)})" if len(found) > 20 else ""
    await message.answer(f"🔎 Найдено: {len(found)}{extra}", reply_markup=kb(rows))