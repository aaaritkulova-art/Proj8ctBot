"""
Парсер текстовых списков задач/корректировок вида:

    1. задача @user ДД.ММ.ГГГГ
    2. задача @user ДД.ММ.ГГГГ

Используется как для /сверка, так и для /протокол — формат ввода
у них одинаковый.
"""
import logging
import re
from typing import List, Dict

from utils.validators import validate_date, validate_username

logger = logging.getLogger(__name__)

# Убирает необязательный префикс с порядковым номером в начале строки: "1.", "1)", "1 -"
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[\.\)\-]?\s*")

# Находит @username и дату ДД.ММ.ГГГГ в оставшейся части строки
_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{4,31})")
_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


def _parse_line(line: str) -> Dict:
    """
    Парсит одну строку списка задач.

    Args:
        line: исходная строка (без ведущего/конечного пробела).

    Returns:
        Словарь с ключами task_text, executor, deadline при успехе,
        либо словарь с ключом "error" при неудаче.
    """
    original = line
    line = _LEADING_NUMBER_RE.sub("", line).strip()

    if not line:
        return {"error": "пустая строка"}

    mention_match = _MENTION_RE.search(line)
    if not mention_match:
        return {"error": "не указан исполнитель (@username)"}

    date_match = _DATE_RE.search(line)
    if not date_match:
        return {"error": "дата должна быть в формате ДД.ММ.ГГГГ"}

    executor_raw = mention_match.group(0)
    executor = validate_username(executor_raw)
    if executor is None:
        return {"error": f"некорректный никнейм исполнителя: {executor_raw}"}

    deadline_raw = date_match.group(1)
    deadline_dt = validate_date(deadline_raw)
    if deadline_dt is None:
        return {"error": f"некорректная дата: {deadline_raw}"}

    # Текст задачи — всё, что стоит до упоминания @username
    task_text = line[: mention_match.start()].strip(" \t-:")
    if not task_text:
        return {"error": "не указан текст задачи"}

    return {
        "task_text": task_text,
        "executor": executor,
        "deadline": deadline_raw,
    }


def parse_task_list(text: str) -> List[Dict]:
    """
    Разбирает многострочный текст со списком задач.

    Каждая строка ожидается в формате:
        "N. текст задачи @исполнитель ДД.ММ.ГГГГ"
    Порядковый номер и пунктуация в начале строки необязательны.

    Строки, которые не удалось распарсить, пропускаются: в
    результирующий список для них добавляется запись с ключом
    "error", описывающим причину, и ключом "line_number",
    "raw" — исходный текст строки. Вызывающий код должен
    отфильтровать такие записи перед сохранением в таблицу и
    сообщить о них пользователю.

    Args:
        text: исходный многострочный текст.

    Returns:
        Список словарей. Успешные строки:
            {"task_text": str, "executor": str, "deadline": str,
             "line_number": int, "raw": str}
        Строки с ошибкой:
            {"error": str, "line_number": int, "raw": str}
    """
    results = []
    lines = text.strip().split("\n")

    for i, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = _parse_line(stripped)
        parsed["line_number"] = i
        parsed["raw"] = stripped
        if "error" in parsed:
            logger.warning("Строка %d не распарсена: %s (%s)", i, parsed["error"], stripped)
        results.append(parsed)

    return results


def split_successful_and_failed(parsed_lines: List[Dict]):
    """
    Разделяет результат parse_task_list на успешно распарсенные
    и ошибочные строки.

    Args:
        parsed_lines: результат parse_task_list.

    Returns:
        Кортеж (successful, failed) — два списка словарей.
    """
    successful = [item for item in parsed_lines if "error" not in item]
    failed = [item for item in parsed_lines if "error" in item]
    return successful, failed
