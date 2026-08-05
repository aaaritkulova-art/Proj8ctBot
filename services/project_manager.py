"""
Сервис бизнес-логики управления проектами.

Оборачивает GoogleSheetsService, добавляя правила уровня приложения:
- определение проекта по chat_id с понятной ошибкой,
- проверку уникальности названия проекта,
- сборку текстовой сводки по проекту.

Использует singleton-подключение к Google Sheets, чтобы не
переавторизовываться при каждом вызове.
"""
import logging
from typing import Optional, Dict, Any

from services.google_sheets import GoogleSheetsService

logger = logging.getLogger(__name__)

_sheets_service: Optional[GoogleSheetsService] = None


def get_sheets_service() -> GoogleSheetsService:
    """
    Возвращает единственный экземпляр GoogleSheetsService,
    создавая его при первом обращении.

    Returns:
        Экземпляр GoogleSheetsService.
    """
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = GoogleSheetsService()
    return _sheets_service


class ProjectNotFoundError(Exception):
    """Проект не найден по chat_id (бот не привязан к проекту в этом чате)."""


class ProjectAlreadyExistsError(Exception):
    """Проект с таким названием уже существует."""


def get_project_or_raise(chat_id: int) -> Dict[str, Any]:
    """
    Находит проект по chat_id или бросает ProjectNotFoundError.

    Args:
        chat_id: ID чата Telegram, из которого пришла команда.

    Returns:
        Словарь с данными проекта.

    Raises:
        ProjectNotFoundError: если проект не найден.
    """
    service = get_sheets_service()
    project = service.get_project_by_chat_id(chat_id)
    if project is None:
        raise ProjectNotFoundError(
            "Я не привязан ни к одному проекту в этом чате. Используйте /новыйпроект."
        )
    return project


def ensure_project_name_available(name: str) -> None:
    """
    Проверяет, что проект с таким названием ещё не существует.

    Args:
        name: название нового проекта.

    Raises:
        ProjectAlreadyExistsError: если проект с таким названием уже есть.
    """
    service = get_sheets_service()
    existing = service.get_project_by_name(name)
    if existing is not None:
        raise ProjectAlreadyExistsError(
            f"Проект с названием «{name}» уже существует. Выберите другое название."
        )


def build_project_summary(project: Dict[str, Any]) -> str:
    """
    Формирует текстовую сводку по проекту для команды /проект.

    Args:
        project: словарь с данными проекта (из get_project_by_chat_id).

    Returns:
        Готовое для отправки в чат сообщение.
    """
    service = get_sheets_service()
    name = project.get("Название проекта", "—")
    stats = service.get_task_stats(name)

    def fmt_list(value: str) -> str:
        if not value or value.strip() in ("-", "нет"):
            return "—"
        return ", ".join(f"@{v.strip().lstrip('@')}" for v in value.split(",") if v.strip())

    lines = [
        f"📌 Проект: {name}",
        f"🚀 Этап: {project.get('Текущий этап', '—') or '—'} | "
        f"Готовность: {project.get('Статус (готовность)', '—') or '—'}",
        f"👤 Менеджер: @{str(project.get('Менеджер', '')).lstrip('@')}"
        if project.get("Менеджер") else "👤 Менеджер: —",
        f"👥 Архитекторы: {fmt_list(project.get('Архитекторы', ''))}",
        f"🎨 Дизайнеры: {fmt_list(project.get('Дизайнеры', ''))}",
        f"🤝 Соучастники: {fmt_list(project.get('Соучастники', ''))}",
        f"📂 Google Диск: {project.get('Ссылка на гугл диск', '—') or '—'}",
        f"📂 Яндекс Диск: {project.get('Ссылка на яндекс диск', '—') or '—'}",
        f"📂 Miro: {project.get('Ссылка на МИРО', '—') or '—'}",
        f"📊 Задачи: Всего: {stats['total']} | В работе: {stats['in_progress']} | "
        f"Просрочено: {stats['overdue']} | Выполнено: {stats['done']}",
    ]
    return "\n".join(lines)
