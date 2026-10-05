"""Конфигурация бота: переменные окружения и константы."""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "vault.db")
# Необязательно: ID через запятую. Если задано — пользоваться ботом смогут только они
# (клиенты по ссылкам-приглашениям всё равно получат свои файлы).
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USERS", "").replace(" ", "").split(",") if x}

FOLDERS_PAGE = 8        # съёмок на странице списка
VIEW_PAGE = 10          # файлов за один показ (лимит альбома Telegram = 10)
MAX_NAME_LEN = 64
MAX_NOTE_LEN = 300
MAX_DEPTH = 4           # максимум уровней вложенности (съёмка = уровень 1)
SEND_DELAY = 0.35       # пауза между отправками, чтобы не упереться в лимиты Telegram
PRESETS = ("Исходники", "Обработанные")

log = logging.getLogger("photovault")