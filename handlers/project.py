"""
Обработчик команды /новыйпроект — пошаговое (FSM) создание проекта
и привязка его к текущему групповому чату.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from services.project_manager import (
    get_sheets_service,
    ensure_project_name_available,
    ProjectAlreadyExistsError,
)
from states.conversation_states import (
    WAITING_PROJECT_NAME,
    WAITING_MANAGER,
    WAITING_DATES,
    WAITING_MEMBERS_ARCHITECTS,
    WAITING_MEMBERS_DESIGNERS,
    WAITING_MEMBERS_PARTNERS,
    WAITING_LINKS_GDRIVE,
    WAITING_LINKS_YANDEX,
    WAITING_LINKS_MIRO,
)
from utils.validators import (
    validate_username,
    validate_username_list,
    validate_date_range,
    is_valid_url,
)

logger = logging.getLogger(__name__)

CANCEL_HINT = "\n\nЧтобы отменить создание проекта, отправьте /cancel."


async def new_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Точка входа: проверяет, что команда вызвана в группе, и запрашивает название."""
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(
            "Эта команда доступна только в группе проекта."
        )
        return ConversationHandler.END

    service = get_sheets_service()
    existing = service.get_project_by_chat_id(update.effective_chat.id)
    if existing is not None:
        await update.effective_message.reply_text(
            f"В этом чате уже привязан проект «{existing.get('Название проекта')}»."
        )
        return ConversationHandler.END

    context.user_data["new_project"] = {"chat_id": update.effective_chat.id}
    await update.effective_message.reply_text(
        "Создаём новый проект. Введите название проекта:" + CANCEL_HINT
    )
    return WAITING_PROJECT_NAME


async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает название проекта, проверяет уникальность."""
    name = update.effective_message.text.strip()
    if not name:
        await update.effective_message.reply_text("Название не может быть пустым. Попробуйте снова.")
        return WAITING_PROJECT_NAME
    try:
        ensure_project_name_available(name)
    except ProjectAlreadyExistsError as e:
        await update.effective_message.reply_text(str(e))
        return WAITING_PROJECT_NAME

    context.user_data["new_project"]["Название проекта"] = name
    await update.effective_message.reply_text(
        "Введите менеджера проекта (тег @username):" + CANCEL_HINT
    )
    return WAITING_MANAGER


async def receive_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает никнейм менеджера проекта."""
    username = validate_username(update.effective_message.text.strip())
    if username is None:
        await update.effective_message.reply_text(
            "Некорректный никнейм. Введите в формате @username (латиница, цифры, подчёркивание)."
        )
        return WAITING_MANAGER

    context.user_data["new_project"]["Менеджер"] = username
    await update.effective_message.reply_text(
        "Введите даты начала и окончания проекта в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ:" + CANCEL_HINT
    )
    return WAITING_DATES


async def receive_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает диапазон дат проекта."""
    date_range = validate_date_range(update.effective_message.text.strip())
    if date_range is None:
        await update.effective_message.reply_text(
            "Ошибка: даты должны быть в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ, "
            "дата начала не позже даты окончания. Попробуйте снова."
        )
        return WAITING_DATES

    context.user_data["new_project"]["Дата начала"] = date_range[0]
    context.user_data["new_project"]["Дата окончания"] = date_range[1]
    await update.effective_message.reply_text(
        "Введите архитекторов проекта через запятую (@user1, @user2), "
        "или «-», если нет:" + CANCEL_HINT
    )
    return WAITING_MEMBERS_ARCHITECTS


async def _receive_member_list(update, context, field_name, next_prompt, next_state):
    """
    Общая логика для приёма списка участников (архитекторы/дизайнеры/соучастники).

    Args:
        field_name: ключ в user_data["new_project"], куда сохранить список.
        next_prompt: текст следующего вопроса.
        next_state: состояние FSM, возвращаемое при успехе.
    """
    usernames = validate_username_list(update.effective_message.text.strip())
    if usernames is None:
        await update.effective_message.reply_text(
            "Некорректный список никнеймов. Введите через запятую в формате "
            "@user1, @user2, либо «-», если пусто."
        )
        return None
    context.user_data["new_project"][field_name] = ", ".join(usernames)
    await update.effective_message.reply_text(next_prompt + CANCEL_HINT)
    return next_state


async def receive_architects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает список архитекторов."""
    result = await _receive_member_list(
        update, context, "Архитекторы",
        "Введите дизайнеров проекта через запятую, или «-», если нет:",
        WAITING_MEMBERS_DESIGNERS,
    )
    return result if result is not None else WAITING_MEMBERS_ARCHITECTS


async def receive_designers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает список дизайнеров."""
    result = await _receive_member_list(
        update, context, "Дизайнеры",
        "Введите соучастников проекта через запятую, или «-», если нет:",
        WAITING_MEMBERS_PARTNERS,
    )
    return result if result is not None else WAITING_MEMBERS_DESIGNERS


async def receive_partners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает список соучастников."""
    result = await _receive_member_list(
        update, context, "Соучастники",
        "Введите ссылку на Google Диск, или «-», если нет:",
        WAITING_LINKS_GDRIVE,
    )
    return result if result is not None else WAITING_MEMBERS_PARTNERS


async def receive_gdrive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает ссылку на Google Диск."""
    link = update.effective_message.text.strip()
    if not is_valid_url(link):
        await update.effective_message.reply_text("Похоже, это не похоже на ссылку. Введите URL или «-».")
        return WAITING_LINKS_GDRIVE
    context.user_data["new_project"]["Ссылка на гугл диск"] = "" if link in ("-", "нет") else link
    await update.effective_message.reply_text("Введите ссылку на Яндекс Диск, или «-», если нет:" + CANCEL_HINT)
    return WAITING_LINKS_YANDEX


async def receive_yandex_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает ссылку на Яндекс Диск."""
    link = update.effective_message.text.strip()
    if not is_valid_url(link):
        await update.effective_message.reply_text("Похоже, это не похоже на ссылку. Введите URL или «-».")
        return WAITING_LINKS_YANDEX
    context.user_data["new_project"]["Ссылка на яндекс диск"] = "" if link in ("-", "нет") else link
    await update.effective_message.reply_text("Введите ссылку на Miro, или «-», если нет:" + CANCEL_HINT)
    return WAITING_LINKS_MIRO


async def receive_miro_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает ссылку на Miro, создаёт проект и завершает диалог."""
    link = update.effective_message.text.strip()
    if not is_valid_url(link):
        await update.effective_message.reply_text("Похоже, это не похоже на ссылку. Введите URL или «-».")
        return WAITING_LINKS_MIRO
    data = context.user_data["new_project"]
    data["Ссылка на МИРО"] = "" if link in ("-", "нет") else link

    service = get_sheets_service()
    try:
        project_id = service.create_project(data)
    except Exception:
        logger.exception("Ошибка при создании проекта")
        await update.effective_message.reply_text(
            "❌ Не удалось создать проект из-за ошибки записи в Google Таблицу. "
            "Попробуйте ещё раз позже."
        )
        context.user_data.pop("new_project", None)
        return ConversationHandler.END

    await update.effective_message.reply_text(
        f"✅ Проект «{data['Название проекта']}» создан! (ID: {project_id})"
    )
    context.user_data.pop("new_project", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий диалог создания проекта."""
    context.user_data.pop("new_project", None)
    await update.effective_message.reply_text("Создание проекта отменено.")
    return ConversationHandler.END
