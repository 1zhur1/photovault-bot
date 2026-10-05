"""Агрегация роутеров обработчиков.

Порядок подключения важен: обработчики проверяются именно в этом порядке.
Команды идут раньше state-обработчиков (например, /cancel должен срабатывать
в любом состоянии), а «ловушки» misc — строго последними.

  1. common — команды (/start, /menu, /cancel, /folders, /stats, /search);
  2. folders — обработчики состояний папок (NewFolder, RenameFolder, ...);
  3. stats — статистика;
  4. files — обработчики состояний загрузки (Upload.active);
  5. share — ссылки для клиентов;
  6. misc — «ловушки» для всего остального (обязательно последним!).

использование:
    from photovault.handlers import router
"""

from aiogram import Router

from . import common, files, folders, misc, share, stats

router = Router()
router.include_router(common.router)
router.include_router(folders.router)
router.include_router(stats.router)
router.include_router(files.router)
router.include_router(share.router)
router.include_router(misc.router)  # последним — иначе fallback перехватит всё

__all__ = ["router"]