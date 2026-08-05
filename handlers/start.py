"""
Обработчики /start, /help и служебное "запоминание" пользователей
(нужно, чтобы позже иметь возможность написать им в ЛС по @username).
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.project_manager import get_sheets_service

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 <b>Бот управления проектами</b>\n\n"
    "Один Telegram-чат = один проект.\n\n"
    "<b>Команды:</b>\n"
    "/newproject — создать проект и привязать к текущей группе\n"
    "/review — добавить список задач по итогам сверки\n"
    "/protocol — добавить список корректировок\n"
    "/mytasks — получить в ЛС свои активные задачи по проекту\n"
    "/alltasks — получить в ЛС все незакрытые задачи проекта\n"
    "/done — отметить свою задачу выполненной\n"
    "/project — показать сводку по проекту в чате\n"
    "/cancel — отменить текущий диалог\n"
    "/help — это сообщение\n\n"
    "ℹ️ Telegram не поддерживает кириллицу в командах, но старые "
    "варианты из ТЗ (/новыйпроект, /сверка, /протокол, /моизадачи, "
    "/всезадачи, /выполнил, /проект, /отмена) тоже работают — бот "
    "распознаёт их как обычный текст.\n\n"
    "⚠️ Чтобы бот мог написать вам в личные сообщения (например, с "
    "уведомлением о новой задаче), сначала напишите ему /start в личке."
)


async def remember_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Запоминает связку @username -> telegram_id при любом сообщении.

    Регистрируется как handler с низким приоритетом (отдельная группа),
    чтобы не мешать остальным обработчикам и не блокировать их.
    """
    user = update.effective_user
    if user is None:
        return
    try:
        service = get_sheets_service()
        service.remember_user(user.username, user.id)
    except Exception:
        logger.exception("Не удалось сохранить пользователя %s", user.id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        text = (
            "👋 Привет! Я бот для управления проектами.\n\n"
            "Добавьте меня в групповой чат проекта и вызовите там "
            "/новыйпроект, чтобы начать. Здесь, в личных сообщениях, "
            "я буду присылать вам уведомления о задачах.\n\n" + HELP_TEXT
        )
    else:
        text = "👋 Привет! Чтобы начать работу с проектом в этом чате, используйте /новыйпроект."
    await update.effective_message.reply_html(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    await update.effective_message.reply_html(HELP_TEXT)
