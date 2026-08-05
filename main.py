"""
Точка входа Telegram-бота для управления проектами.

Собирает все обработчики (команды и FSM-диалоги) и запускает бота
в режиме long polling.

ВАЖНО: Telegram допускает в качестве команд бота только строки из
строчных латинских букв, цифр и подчёркивания (регекс на стороне
Telegram и в самой библиотеке python-telegram-bot: ^[\\da-z_]{1,32}$).
Кириллица в CommandHandler недопустима и вызывает ValueError при
регистрации, а сам Telegram-клиент даже не распознал бы "/новыйпроект"
как команду (entity типа bot_command). Поэтому все команды сделаны
латиницей, а для удобства тех, кто по привычке наберёт кириллический
вариант из исходного ТЗ, добавлены текстовые алиасы — они не являются
"настоящими" командами Telegram, но ловятся как обычный текст и
маршрутизируются на те же обработчики.
"""
import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from handlers import start, project, tasks, protocol, info
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
    WAITING_TASKS_LIST,
    WAITING_PROTOCOL_LIST,
    WAITING_TASK_NUMBER,
)

logger = logging.getLogger(__name__)

# Латинское_имя_команды -> кириллический алиас из исходного ТЗ (для текстового фоллбэка).
COMMAND_ALIASES = {
    "newproject": "новыйпроект",
    "review": "сверка",
    "protocol": "протокол",
    "mytasks": "моизадачи",
    "alltasks": "всезадачи",
    "done": "выполнил",
    "project": "проект",
    "cancel": "отмена",
}


def entry_points(latin: str, callback) -> list:
    """
    Строит список entry_points/handlers: реальная Telegram-команда на
    латинице + текстовый фоллбэк на кириллический вариант из ТЗ.

    Args:
        latin: латинское имя команды (без "/").
        callback: обработчик, который нужно вызвать.

    Returns:
        Список handler'ов для использования в CommandHandler-местах.
    """
    handlers_list = [CommandHandler(latin, callback)]
    cyrillic = COMMAND_ALIASES.get(latin)
    if cyrillic:
        pattern = rf"(?i)^/{cyrillic}(?:@\w+)?\s*$"
        handlers_list.append(MessageHandler(filters.Regex(pattern), callback))
    return handlers_list


def build_new_project_conversation() -> ConversationHandler:
    """Собирает ConversationHandler для команды /newproject (алиас: /новыйпроект)."""
    return ConversationHandler(
        entry_points=entry_points("newproject", project.new_project_start),
        states={
            WAITING_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_project_name)],
            WAITING_MANAGER: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_manager)],
            WAITING_DATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_dates)],
            WAITING_MEMBERS_ARCHITECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_architects)],
            WAITING_MEMBERS_DESIGNERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_designers)],
            WAITING_MEMBERS_PARTNERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_partners)],
            WAITING_LINKS_GDRIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_gdrive_link)],
            WAITING_LINKS_YANDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_yandex_link)],
            WAITING_LINKS_MIRO: [MessageHandler(filters.TEXT & ~filters.COMMAND, project.receive_miro_link)],
        },
        fallbacks=entry_points("cancel", project.cancel),
        name="new_project_conversation",
    )


def build_review_conversation() -> ConversationHandler:
    """Собирает ConversationHandler для команды /review (алиас: /сверка)."""
    return ConversationHandler(
        entry_points=entry_points("review", tasks.review_command),
        states={
            WAITING_TASKS_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, tasks.review_list)],
        },
        fallbacks=entry_points("cancel", tasks.cancel),
        name="review_conversation",
    )


def build_protocol_conversation() -> ConversationHandler:
    """Собирает ConversationHandler для команды /protocol (алиас: /протокол)."""
    return ConversationHandler(
        entry_points=entry_points("protocol", protocol.protocol_command),
        states={
            WAITING_PROTOCOL_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, protocol.protocol_list)],
        },
        fallbacks=entry_points("cancel", protocol.cancel),
        name="protocol_conversation",
    )


def build_complete_task_conversation() -> ConversationHandler:
    """Собирает ConversationHandler для команды /done (алиас: /выполнил)."""
    return ConversationHandler(
        entry_points=entry_points("done", tasks.complete_task_start),
        states={
            WAITING_TASK_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, tasks.complete_task_number)],
        },
        fallbacks=entry_points("cancel", tasks.cancel),
        name="complete_task_conversation",
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик необработанных исключений.

    Логирует ошибку и, если возможно, отправляет пользователю
    понятное сообщение вместо падения бота.
    """
    logger.error("Необработанная ошибка при обработке update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла непредвиденная ошибка. Попробуйте ещё раз чуть позже."
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение об ошибке пользователю.")


def main() -> None:
    """Собирает приложение и запускает polling."""
    config.setup_logging()
    config.validate_config()

    application: Application = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Запоминаем пользователей на каждом сообщении (для резолва @username -> id).
    # group=-1, чтобы отработать раньше остальных обработчиков и не блокировать их.
    application.add_handler(MessageHandler(filters.ALL, start.remember_user), group=-1)

    application.add_handler(CommandHandler("start", start.start_command))
    application.add_handler(CommandHandler("help", start.help_command))

    application.add_handler(build_new_project_conversation())
    application.add_handler(build_review_conversation())
    application.add_handler(build_protocol_conversation())
    application.add_handler(build_complete_task_conversation())

    for handler in entry_points("mytasks", tasks.my_tasks):
        application.add_handler(handler)
    for handler in entry_points("alltasks", tasks.all_tasks):
        application.add_handler(handler)
    for handler in entry_points("project", info.project_info_command):
        application.add_handler(handler)

    application.add_error_handler(error_handler)

    logger.info("Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
