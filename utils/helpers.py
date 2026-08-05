"""
Вспомогательные функции общего назначения.
"""
from datetime import datetime
from typing import Optional

from telegram import Update

from config import DATE_FORMAT, STATUS_IN_PROGRESS, STATUS_OVERDUE, STATUS_DONE


def today_str() -> str:
    """Возвращает сегодняшнюю дату в формате ДД.ММ.ГГГГ."""
    return datetime.now().strftime(DATE_FORMAT)


def is_overdue(deadline_str: str, current_status: str) -> bool:
    """
    Определяет, просрочена ли задача с данным сроком.

    Задача считается просроченной, если её текущий статус — "В работе"
    и срок выполнения уже прошёл (строго раньше сегодняшнего дня).
    Уже выполненные задачи никогда не считаются просроченными.

    Args:
        deadline_str: срок выполнения в формате ДД.ММ.ГГГГ.
        current_status: текущий статус задачи.

    Returns:
        True, если задачу следует считать просроченной.
    """
    if current_status == STATUS_DONE:
        return False
    try:
        deadline = datetime.strptime(deadline_str, DATE_FORMAT)
    except (ValueError, TypeError):
        return False
    return deadline.date() < datetime.now().date()


def effective_status(deadline_str: str, stored_status: str) -> str:
    """
    Вычисляет актуальный статус задачи "на лету", не изменяя таблицу.

    Args:
        deadline_str: срок выполнения задачи.
        stored_status: статус, сохранённый в Google Таблице.

    Returns:
        STATUS_OVERDUE, если задача просрочена и ещё не выполнена,
        иначе — исходный статус из таблицы.
    """
    if stored_status == STATUS_DONE:
        return STATUS_DONE
    if is_overdue(deadline_str, stored_status):
        return STATUS_OVERDUE
    return STATUS_IN_PROGRESS


def get_username(update: Update) -> Optional[str]:
    """
    Извлекает username пользователя, вызвавшего команду.

    Args:
        update: объект Update от telegram.

    Returns:
        Никнейм пользователя (без "@") в нижнем регистре,
        либо None, если у пользователя не задан username.
    """
    user = update.effective_user
    if user is None or not user.username:
        return None
    return user.username.lower()


def format_task_line(index: int, task: dict, show_executor: bool = False) -> str:
    """
    Форматирует одну строку задачи для вывода пользователю.

    Args:
        index: порядковый номер для отображения.
        task: словарь с ключами task_text, executor, deadline, status.
        show_executor: включать ли исполнителя в строку.

    Returns:
        Готовая для вывода строка.
    """
    status = task.get("status", STATUS_IN_PROGRESS)
    line = f"{index}. {task.get('task_text', '')}"
    if show_executor:
        line += f" | Исполнитель: @{task.get('executor', '')}"
    line += f" | Срок: {task.get('deadline', '')}"
    if status == STATUS_OVERDUE:
        line += " | ⚠️ ПРОСРОЧЕНО"
    else:
        line += f" | Статус: {status}"
    return line


def chunk_text(text: str, limit: int = 4000) -> list:
    """
    Разбивает длинный текст на части не длиннее лимита Telegram-сообщения.

    Разбиение происходит по границам строк, чтобы не разрывать задачи
    посередине.

    Args:
        text: исходный текст.
        limit: максимальная длина одной части.

    Returns:
        Список частей текста.
    """
    if len(text) <= limit:
        return [text]
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks
