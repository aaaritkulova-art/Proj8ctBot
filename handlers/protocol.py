"""
Обработчик команды /протокол — добавление списка корректировок.
Формат ввода идентичен /сверка, но записи идут на лист "Протоколы".
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from services.project_manager import get_project_or_raise, ProjectNotFoundError, get_sheets_service
from services.task_parser import parse_task_list, split_successful_and_failed
from states.conversation_states import WAITING_PROTOCOL_LIST
from handlers.tasks import _notify_executor

logger = logging.getLogger(__name__)


async def protocol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Точка входа команды /протокол."""
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(
            "Эта команда доступна только в группе проекта."
        )
        return ConversationHandler.END

    try:
        project = get_project_or_raise(update.effective_chat.id)
    except ProjectNotFoundError as e:
        await update.effective_message.reply_text(str(e))
        return ConversationHandler.END

    context.user_data["protocol_project"] = project.get("Название проекта")
    await update.effective_message.reply_text(
        "Отправьте список корректировок в формате:\n"
        "1. Описание @user ДД.ММ.ГГГГ\n"
        "2. Описание @user ДД.ММ.ГГГГ\n\n"
        "Чтобы отменить, отправьте /cancel."
    )
    return WAITING_PROTOCOL_LIST


async def protocol_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает и обрабатывает список корректировок для /протокол."""
    project_name = context.user_data.get("protocol_project")
    if not project_name:
        await update.effective_message.reply_text("Что-то пошло не так, начните заново: /протокол")
        return ConversationHandler.END

    parsed = parse_task_list(update.effective_message.text)
    successful, failed = split_successful_and_failed(parsed)

    for item in failed:
        await update.effective_message.reply_text(
            f"Ошибка в строке {item['line_number']}: {item['error']}. Строка пропущена."
        )

    if not successful:
        await update.effective_message.reply_text(
            "Ни одна строка не была распознана. Попробуйте отправить список заново, "
            "или /cancel для выхода."
        )
        return WAITING_PROTOCOL_LIST

    service = get_sheets_service()
    service.add_protocol_entries(project_name, successful)

    for entry in successful:
        await _notify_executor(context, project_name, entry, kind="корректировка")

    await update.effective_message.reply_text(
        f"✅ Зафиксировано {len(successful)} корректировок."
    )
    context.user_data.pop("protocol_project", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий диалог создания протокола."""
    context.user_data.pop("protocol_project", None)
    await update.effective_message.reply_text("Действие отменено.")
    return ConversationHandler.END
