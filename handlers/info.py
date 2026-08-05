"""
Обработчик команды /проект — показывает сводку по проекту в чате.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.project_manager import get_project_or_raise, ProjectNotFoundError, build_project_summary

logger = logging.getLogger(__name__)


async def project_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /проект."""
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(
            "Эта команда доступна только в группе проекта."
        )
        return

    try:
        project = get_project_or_raise(update.effective_chat.id)
    except ProjectNotFoundError as e:
        await update.effective_message.reply_text(str(e))
        return

    try:
        summary = build_project_summary(project)
    except Exception:
        logger.exception("Ошибка при формировании сводки проекта")
        await update.effective_message.reply_text(
            "❌ Не удалось получить данные проекта из Google Таблицы. Попробуйте позже."
        )
        return

    await update.effective_message.reply_text(summary)
