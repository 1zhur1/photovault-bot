"""Небольшие утилиты: экранирование HTML, обрезка строк, формат размера."""

import html


def esc(s: str) -> str:
    return html.escape(s or "")


def short(s: str, n: int = 40) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def clean_name(raw: str) -> str:
    return " ".join(raw.split())


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} Б"