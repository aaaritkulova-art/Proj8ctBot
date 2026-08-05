"""
Функции валидации входных данных: дат, никнеймов и т.д.
"""
import re
from datetime import datetime
from typing import Optional

from config import DATE_FORMAT

# Никнейм Telegram: 5-32 символа, латиница, цифры, подчёркивание,
# не может начинаться с цифры.
USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{4,31}$")

# Дата в формате ДД.ММ.ГГГГ
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

# Диапазон дат: "ДД.ММ.ГГГГ - ДД.ММ.ГГГГ" (разделитель — дефис, длинное или короткое тире)
DATE_RANGE_RE = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s*[-–—]\s*(\d{2}\.\d{2}\.\d{4})$"
)


def validate_date(date_str: str) -> Optional[datetime]:
    """
    Проверяет и парсит дату в формате ДД.ММ.ГГГГ.

    Args:
        date_str: строка с датой.

    Returns:
        Объект datetime, если строка валидна, иначе None.
    """
    date_str = date_str.strip()
    if not DATE_RE.match(date_str):
        return None
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        return None


def validate_date_range(text: str) -> Optional[tuple]:
    """
    Проверяет и парсит диапазон дат "ДД.ММ.ГГГГ - ДД.ММ.ГГГГ".

    Args:
        text: строка с диапазоном дат.

    Returns:
        Кортеж (start_str, end_str), если строка валидна и обе даты
        корректны (start <= end), иначе None.
    """
    match = DATE_RANGE_RE.match(text.strip())
    if not match:
        return None
    start_str, end_str = match.group(1), match.group(2)
    start_dt = validate_date(start_str)
    end_dt = validate_date(end_str)
    if not start_dt or not end_dt:
        return None
    if start_dt > end_dt:
        return None
    return start_str, end_str


def validate_username(username: str) -> Optional[str]:
    """
    Проверяет формат никнейма Telegram (@username).

    Args:
        username: строка с никнеймом (с "@" или без).

    Returns:
        Никнейм без "@" в нижнем регистре, если валиден, иначе None.
    """
    username = username.strip()
    if not USERNAME_RE.match(username):
        return None
    return username.lstrip("@").lower()


def validate_username_list(text: str) -> Optional[list]:
    """
    Парсит список никнеймов, разделённых запятой, пробелом или переносом строки.

    Args:
        text: строка со списком никнеймов, либо "-"/"нет" для пустого списка.

    Returns:
        Список валидных никнеймов (без "@"), либо None, если хотя бы
        один никнейм в списке некорректен. Пустой список, если введено
        "-" или "нет".
    """
    text = text.strip()
    if text.lower() in ("-", "нет", "none"):
        return []
    raw_items = re.split(r"[,\s\n]+", text)
    raw_items = [item for item in raw_items if item]
    result = []
    for item in raw_items:
        username = validate_username(item)
        if username is None:
            return None
        result.append(username)
    return result


def is_valid_url(text: str) -> bool:
    """
    Простая проверка, похожа ли строка на URL, либо это плейсхолдер "-".

    Args:
        text: строка со ссылкой.

    Returns:
        True, если строка похожа на URL или является плейсхолдером "-"/"нет".
    """
    text = text.strip()
    if text.lower() in ("-", "нет", "none"):
        return True
    return bool(re.match(r"^https?://\S+$", text))
