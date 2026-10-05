"""Слой работы с базой данных SQLite (aiosqlite): схема, миграции, запросы."""

from contextlib import asynccontextmanager

import aiosqlite

from .config import DB_PATH
from .tree import Tree


def folders_ddl(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        parent_id   INTEGER NOT NULL DEFAULT 0,      -- 0 = корневая папка (съёмка)
        name        TEXT    NOT NULL,
        note        TEXT,
        share_token TEXT UNIQUE,
        created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, parent_id, name)
    );
    """


SCHEMA = folders_ddl("folders") + """
CREATE TABLE IF NOT EXISTS files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id      INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL,
    file_id        TEXT    NOT NULL,
    file_unique_id TEXT    NOT NULL,
    kind           TEXT    NOT NULL,           -- photo | video | document
    file_name      TEXT,
    file_size      INTEGER,
    batch          INTEGER NOT NULL DEFAULT 0, -- номер пачки загрузки (для отмены)
    added_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (folder_id, file_unique_id)
);
CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id, id);
CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id, parent_id);
"""

# Миграция со старой версии (папки без вложенности).
MIGRATE_V1 = (
    "PRAGMA foreign_keys = OFF; BEGIN;"
    + folders_ddl("folders_new")
    + """
    INSERT INTO folders_new (id, user_id, parent_id, name, created_at)
        SELECT id, user_id, 0, name, created_at FROM folders;
    DROP TABLE folders;
    ALTER TABLE folders_new RENAME TO folders;
    COMMIT; PRAGMA foreign_keys = ON;
    """
)


@asynccontextmanager
async def conn():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("PRAGMA table_info(folders)")
        cols = {r[1] for r in await cur.fetchall()}
        if cols and "parent_id" not in cols:
            await db.executescript(MIGRATE_V1)
        cur = await db.execute("PRAGMA table_info(files)")
        fcols = {r[1] for r in await cur.fetchall()}
        if fcols and "batch" not in fcols:
            await db.execute("ALTER TABLE files ADD COLUMN batch INTEGER NOT NULL DEFAULT 0")
        await db.executescript(SCHEMA)
        await db.commit()


async def load_tree(user_id: int) -> Tree:
    async with conn() as db:
        cur = await db.execute(
            """SELECT id, parent_id, name, note, share_token, created_at
               FROM folders WHERE user_id = ? ORDER BY id""",
            (user_id,),
        )
        folders = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute(
            "SELECT folder_id, COUNT(*) AS c FROM files WHERE user_id = ? GROUP BY folder_id",
            (user_id,),
        )
        own = {r["folder_id"]: r["c"] for r in await cur.fetchall()}
    return Tree(folders, own)


async def create_folder(user_id: int, parent_id: int, name: str) -> int | None:
    async with conn() as db:
        try:
            cur = await db.execute(
                "INSERT INTO folders (user_id, parent_id, name) VALUES (?, ?, ?)",
                (user_id, parent_id, name),
            )
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def rename_folder(user_id: int, folder_id: int, name: str) -> bool:
    async with conn() as db:
        try:
            cur = await db.execute(
                "UPDATE folders SET name = ? WHERE id = ? AND user_id = ?", (name, folder_id, user_id)
            )
            await db.commit()
            return cur.rowcount > 0
        except aiosqlite.IntegrityError:
            return False


async def set_note(user_id: int, folder_id: int, note: str | None) -> None:
    async with conn() as db:
        await db.execute(
            "UPDATE folders SET note = ? WHERE id = ? AND user_id = ?", (note, folder_id, user_id)
        )
        await db.commit()


async def set_share_token(user_id: int, folder_id: int, token: str | None) -> None:
    async with conn() as db:
        await db.execute(
            "UPDATE folders SET share_token = ? WHERE id = ? AND user_id = ?", (token, folder_id, user_id)
        )
        await db.commit()


async def get_folder_by_token(token: str):
    async with conn() as db:
        cur = await db.execute(
            "SELECT id, user_id, name FROM folders WHERE share_token = ?", (token,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def delete_folders(user_id: int, ids: list[int]) -> None:
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    async with conn() as db:
        # файлы удаляются каскадом (ON DELETE CASCADE)
        await db.execute(
            f"DELETE FROM folders WHERE user_id = ? AND id IN ({marks})", (user_id, *ids)
        )
        await db.commit()


async def add_file(folder_id: int, user_id: int, kind: str, file_id: str, unique_id: str,
                   file_name: str | None, size: int | None, batch: int) -> bool:
    """True — файл добавлен, False — такой файл уже есть в папке."""
    async with conn() as db:
        try:
            await db.execute(
                """INSERT INTO files
                   (folder_id, user_id, file_id, file_unique_id, kind, file_name, file_size, batch)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (folder_id, user_id, file_id, unique_id, kind, file_name, size, batch),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def undo_batch(user_id: int, folder_id: int, batch: int) -> int:
    async with conn() as db:
        cur = await db.execute(
            "DELETE FROM files WHERE user_id = ? AND folder_id = ? AND batch = ?",
            (user_id, folder_id, batch),
        )
        await db.commit()
        return cur.rowcount


async def get_files(folder_id: int, offset: int, limit: int):
    async with conn() as db:
        cur = await db.execute(
            "SELECT kind, file_id FROM files WHERE folder_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (folder_id, limit, offset),
        )
        return await cur.fetchall()


async def count_by_kind(folder_id: int) -> dict[str, int]:
    async with conn() as db:
        cur = await db.execute(
            "SELECT kind, COUNT(*) AS c FROM files WHERE folder_id = ? GROUP BY kind", (folder_id,)
        )
        data = {r["kind"]: r["c"] for r in await cur.fetchall()}
    return {k: data.get(k, 0) for k in ("photo", "video", "document")}


async def get_stats(user_id: int) -> dict:
    async with conn() as db:
        cur = await db.execute(
            """SELECT kind, COUNT(*) AS c, COALESCE(SUM(file_size), 0) AS s
               FROM files WHERE user_id = ? GROUP BY kind""",
            (user_id,),
        )
        kinds = {r["kind"]: (r["c"], r["s"]) for r in await cur.fetchall()}
        cur = await db.execute("SELECT COUNT(*) FROM folders WHERE user_id = ?", (user_id,))
        folders = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM folders WHERE user_id = ? AND parent_id = 0", (user_id,)
        )
        roots = (await cur.fetchone())[0]
    return {"kinds": kinds, "folders": folders, "roots": roots}