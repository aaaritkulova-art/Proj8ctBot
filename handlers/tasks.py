"""
Обработчики команд, связанных с задачами: /сверка, /моизадачи,
/всезадачи, /выполнил.
"""
import logging

from telegram import Update
from telegram.error import Forbidden, BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from services.project_manager import (
    get_sheets_service,
    get_project_or_raise,
    ProjectNotFoundError,
)
from services.task_parser import parse_task_list, split_successful_and_failed
from states.conversation_states import WAITING_TASKS_LIST, WAITING_TASK_NUMBER
from utils.helpers import get_username, format_task_line, chunk_text

logger = logging.getLogger(__name__)


async def _require_group_project(update: Update):
    """
    Общая проверка: команда должна вызываться в группе, привязанной к проекту.

    Returns:
        Словарь с данными проекта, либо None (в этом случае ошибка
        уже отправлена пользователю).
    """
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(
            "Эта команда доступна только в группе проекта."
        )
        return None
    try:
        return get_project_or_raise(update.effective_chat.id)
    except ProjectNotFoundError as e:
        await update.effective_message.reply_text(str(e))
        return None


async def _notify_executor(context: ContextTypes.DEFAULT_TYPE, project_name: str, task: dict, kind: str) -> None:
    """
    Отправляет исполнителю личное сообщение о новой задаче/корректировке.

    Args:
        project_name: название проекта.
        task: словарь с ключами task_text, executor, deadline.
        kind: "задача" или "корректировка" — для текста сообщения.
    """
    service = get_sheets_service()
    telegram_id = service.get_telegram_id(task["executor"])
    if telegram_id is None:
        logger.info(
            "Не удалось уведомить @%s — пользователь ещё не писал боту.", task["executor"]
        )
        return
    if kind == "задача":
        text = (
            f"В проекте «{project_name}» вам назначена задача: "
            f"{task['task_text']}. Срок: {task['deadline']}."
        )
    else:
        text = (
            f"В проекте «{project_name}» зафиксирована корректировка: "
            f"{task['task_text']}. Срок: {task['deadline']}."
        )
    try:
        await context.bot.send_message(chat_id=telegram_id, text=text)
    except (Forbidden, BadRequest):
        logger.info("Не удалось отправить ЛС пользователю @%s (%s)", task["executor"], telegram_id)


# ----------------------------------------------------------------------
# /сверка
# ----------------------------------------------------------------------

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Точка входа команды /сверка."""
    project = await _require_group_project(update)
    if project is None:
        return ConversationHandler.END

    context.user_data["review_project"] = project.get("Название проекта")
    await update.effective_message.reply_text(
        "Отправьте список задач в формате:\n"
        "1. задача @user ДД.ММ.ГГГГ\n"
        "2. задача @user ДД.ММ.ГГГГ\n\n"
        "Чтобы отменить, отправьте /cancel."
    )
    return WAITING_TASKS_LIST


async def review_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает и обрабатывает список задач для /сверка."""
    project_name = context.user_data.get("review_project")
    if not project_name:
        await update.effective_message.reply_text("Что-то пошло не так, начните заново: /сверка")
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
        return WAITING_TASKS_LIST

    service = get_sheets_service()
    service.add_tasks_bulk(project_name, successful)

    for task in successful:
        await _notify_executor(context, project_name, task, kind="задача")

    await update.effective_message.reply_text(
        f"✅ Добавлено {len(successful)} задач. Исполнители уведомлены."
    )
    context.user_data.pop("review_project", None)
    return ConversationHandler.END


# ----------------------------------------------------------------------
# /моизадачи
# ----------------------------------------------------------------------

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /моизадачи — отправляет задачи пользователя в ЛС."""
    project = await _require_group_project(update)
    if project is None:
        return

    username = get_username(update)
    if username is None:
        await update.effective_message.reply_text(
            "У вас не задан @username в Telegram — не могу определить ваши задачи. "
            "Установите username в настройках Telegram и повторите."
        )
        return

    service = get_sheets_service()
    project_name = project.get("Название проекта")
    tasks = service.get_user_tasks(project_name, username)

    if not tasks:
        text = f"🎉 В проекте «{project_name}» у вас нет активных задач."
    else:
        lines = [f"Ваши задачи в проекте «{project_name}»:"]
        for i, task in enumerate(tasks, start=1):
            lines.append(format_task_line(i, {
                "task_text": task.get("Задача", ""),
                "deadline": task.get("Срок выполнения задачи", ""),
                "status": task.get("Статус задачи", ""),
            }))
        text = "\n".join(lines)

    await _send_dm_or_notify(update, context, text)


# ----------------------------------------------------------------------
# /всезадачи
# ----------------------------------------------------------------------

async def all_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /всезадачи — отправляет все незакрытые задачи в ЛС."""
    project = await _require_group_project(update)
    if project is None:
        return

    service = get_sheets_service()
    project_name = project.get("Название проекта")
    tasks = service.get_all_tasks(project_name)

    if not tasks:
        text = f"🎉 В проекте «{project_name}» нет незакрытых задач."
    else:
        lines = [
            f"📋 Все незакрытые задачи в проекте «{project_name}»:",
            "📅 Сортировка: по сроку выполнения",
            "",
        ]
        for i, task in enumerate(tasks, start=1):
            lines.append(format_task_line(i, {
                "task_text": task.get("Задача", ""),
                "executor": task.get("Исполнитель", ""),
                "deadline": task.get("Срок выполнения задачи", ""),
                "status": task.get("Статус задачи", ""),
            }, show_executor=True))
        lines.append("")
        lines.append(f"📊 Итого: {len(tasks)} задач")
        text = "\n".join(lines)

    await _send_dm_or_notify(update, context, text)


async def _send_dm_or_notify(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """
    Пытается отправить текст пользователю в ЛС; если это не удаётся
    (пользователь ещё не писал боту), сообщает об этом в группе.
    """
    user = update.effective_user
    try:
        for chunk in chunk_text(text):
            await context.bot.send_message(chat_id=user.id, text=chunk)
        if update.effective_chat.type != "private":
            await update.effective_message.reply_text("📨 Отправил вам сообщение в личные сообщения.")
    except (Forbidden, BadRequest):
        await update.effective_message.reply_text(
            "Не удалось отправить вам личное сообщение. Пожалуйста, напишите боту "
            "/start в личных сообщениях и повторите команду."
        )


# ----------------------------------------------------------------------
# /выполнил
# ----------------------------------------------------------------------

async def complete_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Точка входа команды /выполнил. Работает и в группе, и в ЛС —
    в ЛС проект нужно определить иначе, поэтому в этой реализации
    команда полноценно работает только в группе проекта
    (см. обработку ошибок ниже).
    """
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(
            "Используйте /выполнил в группе проекта, чтобы я мог определить, "
            "к какому проекту относится задача."
        )
        return ConversationHandler.END

    try:
        project = get_project_or_raise(update.effective_chat.id)
    except ProjectNotFoundError as e:
        await update.effective_message.reply_text(str(e))
        return ConversationHandler.END

    username = get_username(update)
    if username is None:
        await update.effective_message.reply_text(
            "У вас не задан @username в Telegram — не могу определить ваши задачи."
        )
        return ConversationHandler.END

    service = get_sheets_service()
    project_name = project.get("Название проекта")
    tasks = service.get_user_tasks(project_name, username)

    if not tasks:
        await update.effective_message.reply_text("У вас нет незакрытых задач в этом проекте.")
        return ConversationHandler.END

    lines = [f"Ваши незакрытые задачи в проекте «{project_name}»:"]
    task_map = {}
    for i, task in enumerate(tasks, start=1):
        lines.append(format_task_line(i, {
            "task_text": task.get("Задача", ""),
            "deadline": task.get("Срок выполнения задачи", ""),
            "status": task.get("Статус задачи", ""),
        }))
        task_map[i] = task
    lines.append("\nВведите номер задачи, которую вы выполнили.")

    context.user_data["complete_task_project"] = project_name
    context.user_data["complete_task_map"] = {i: t.get("Номер") for i, t in task_map.items()}
    await update.effective_message.reply_text("\n".join(lines))
    return WAITING_TASK_NUMBER


async def complete_task_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает номер (из показанного списка) и отмечает задачу выполненной."""
    text = update.effective_message.text.strip()
    task_map = context.user_data.get("complete_task_map", {})
    project_name = context.user_data.get("complete_task_project")

    try:
        display_number = int(text)
    except ValueError:
        await update.effective_message.reply_text(
            f"Задача с номером {text} не найдена. Попробуйте снова."
        )
        return WAITING_TASK_NUMBER

    real_number = task_map.get(display_number)
    if real_number is None:
        await update.effective_message.reply_text(
            f"Задача с номером {display_number} не найдена. Попробуйте снова."
        )
        return WAITING_TASK_NUMBER

    username = get_username(update)
    service = get_sheets_service()
    task = service.complete_task(project_name, real_number, username)

    if task is None:
        await update.effective_message.reply_text(
            f"Задача с номером {display_number} не найдена. Попробуйте снова."
        )
        return WAITING_TASK_NUMBER

    await update.effective_message.reply_text(
        f"✅ Задача «{task.get('Задача')}» отмечена как выполненная."
    )
    context.user_data.pop("complete_task_map", None)
    context.user_data.pop("complete_task_project", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий диалог (сверка или выполнил)."""
    context.user_data.pop("review_project", None)
    context.user_data.pop("complete_task_map", None)
    context.user_data.pop("complete_task_project", None)
    await update.effective_message.reply_text("Действие отменено.")
    return ConversationHandler.END
