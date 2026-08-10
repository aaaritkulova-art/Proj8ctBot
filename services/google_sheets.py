"""
Слой взаимодействия с Google Sheets.

Инкапсулирует всю работу с gspread: чтение и запись строк на трёх
(фактически — четырёх, см. ниже) листах таблицы.

ВАЖНО, чего нет в исходном ТЗ, но необходимо технически:
Telegram Bot API не позволяет отправить пользователю личное
сообщение, зная только его @username — нужен числовой telegram_id,
а его можно узнать только после того, как пользователь хотя бы
раз написал боту (например, /start) или после первого сообщения
в группе, где бот его увидел. Поэтому добавлен четвёртый служебный
лист "Пользователи" (username -> telegram_id), который наполняется
автоматически при любом взаимодействии пользователя с ботом.
Это не меняет три листа из ТЗ, а дополняет их.
"""
import json
import os
import tempfile
import logging
from typing import Optional, List, Dict, Any

import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
    SHEET_PROJECT_INFO,
    SHEET_TASKS,
    SHEET_PROTOCOLS,
    STATUS_IN_PROGRESS,
    STATUS_DONE,
)
from utils.helpers import today_str, effective_status

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_USERS = "Пользователи"

# Заголовки листов. Порядок соответствует фактическому порядку колонок
# в таблице (важно для совместимости с дашбордом — см. project_dashboard).
PROJECT_INFO_HEADERS = [
    "Состояние проекта",              # 🔴/🟡/🟢/⚪ — заполняется вручную, для дашборда
    "Статус проекта",                 # Не начат/В работе/.../Закончен — вручную, для дашборда
    "ID",
    "Название проекта",
    "Текущий этап",
    "Статус (готовность)",
    "Вопросы к Диме",
    "Вопросы к Наде",
    "Дорожная карта (ссылка)",
    "Дата начала",
    "Дата окончания",
    "chat_id",
    "Ссылка на гугл диск",
    "Ссылка на яндекс диск",
    "Ссылка на МИРО",
    "Официальное ТЗ на проект",
    "Папка для передачи заказчику",
    "Менеджер",
    "Архитекторы",
    "Дизайнеры",
    "Соучастники",
]

TASKS_HEADERS = [
    "Номер",
    "Дата сверки",
    "Задача",
    "Исполнитель",
    "Срок выполнения задачи",
    "Статус задачи",
    "project_name",
]

PROTOCOLS_HEADERS = [
    "Дата сверки",
    "Корректировки",
    "Исполнитель",
    "Срок",
    "Статус",
    "project_name",
]

USERS_HEADERS = ["username", "telegram_id"]


class GoogleSheetsService:
    """Сервис для чтения и записи данных проектов в Google Sheets."""

    def __init__(self):
        """
        Устанавливает соединение с Google Sheets API и открывает
        рабочие листы, создавая их (с заголовками) при отсутствии.

        Сервисный ключ читается из переменной окружения
        GOOGLE_CREDENTIALS_JSON (содержимое JSON-файла целиком — так
        удобно на хостингах вроде Railway, где нет файлового доступа),
        а если она не задана — из файла по пути GOOGLE_CREDENTIALS_FILE
        (удобно для локальной разработки).
        """
        temp_path = None
        
        try:
            if GOOGLE_CREDENTIALS_JSON:
                logger.info("📄 Загрузка credentials из переменной GOOGLE_CREDENTIALS_JSON...")
                
                # Парсим JSON
                creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
                
                # КРИТИЧЕСКИ ВАЖНО: Исправляем private_key
                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
                    logger.info("✅ private_key исправлена")
                
                # Создаём временный файл (это 100% решает проблему с \n)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(creds_dict, f)
                    temp_path = f.name
                    logger.info(f"✅ Временный файл создан: {temp_path}")
                
                # Загружаем credentials ИЗ ФАЙЛА (не из строки!)
                credentials = Credentials.from_service_account_file(
                    temp_path,
                    scopes=SCOPES
                )
                logger.info("✅ Credentials загружены из временного файла")
                
            else:
                logger.info("📄 Загрузка credentials из файла: %s", GOOGLE_CREDENTIALS_FILE)
                credentials = Credentials.from_service_account_file(
                    GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
                )
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка создания credentials: {e}")
            raise
        finally:
            # Удаляем временный файл
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    logger.info("🧹 Временный файл удалён")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить временный файл: {e}")
        
        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)

        self.ws_project_info = self._get_or_create_worksheet(
            SHEET_PROJECT_INFO, PROJECT_INFO_HEADERS
        )
        self.ws_tasks = self._get_or_create_worksheet(SHEET_TASKS, TASKS_HEADERS)
        self.ws_protocols = self._get_or_create_worksheet(
            SHEET_PROTOCOLS, PROTOCOLS_HEADERS
        )
        self.ws_users = self._get_or_create_worksheet(SHEET_USERS, USERS_HEADERS)
        logger.info("Подключение к Google Sheets установлено.")

    def _get_or_create_worksheet(self, title: str, headers: List[str]):
        """
        Возвращает лист таблицы по названию, создавая его с заголовками,
        если он ещё не существует.

        Args:
            title: название листа.
            headers: заголовки, которые нужно записать при создании.

        Returns:
            Объект worksheet gspread.
        """
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            logger.info("Лист '%s' не найден, создаю новый.", title)
            ws = self.spreadsheet.add_worksheet(
                title=title, rows=1000, cols=max(len(headers), 10)
            )
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws

    # ------------------------------------------------------------------
    # Пользователи (для резолва @username -> telegram_id)
    # ------------------------------------------------------------------

    def remember_user(self, username: Optional[str], telegram_id: int) -> None:
        """
        Сохраняет или обновляет соответствие username -> telegram_id.

        Args:
            username: никнейм пользователя без "@" (может отсутствовать).
            telegram_id: числовой ID пользователя в Telegram.
        """
        if not username:
            return
        username = username.lower()
        records = self.ws_users.get_all_records()
        for i, record in enumerate(records, start=2):
            if str(record.get("username", "")).lower() == username:
                if str(record.get("telegram_id")) != str(telegram_id):
                    self.ws_users.update_cell(i, 2, telegram_id)
                return
        self.ws_users.append_row([username, telegram_id], value_input_option="USER_ENTERED")

    def get_telegram_id(self, username: str) -> Optional[int]:
        """
        Ищет telegram_id пользователя по его @username.

        Args:
            username: никнейм пользователя без "@".

        Returns:
            Числовой telegram_id, либо None, если пользователь ещё
            ни разу не взаимодействовал с ботом.
        """
        username = username.lower().lstrip("@")
        records = self.ws_users.get_all_records()
        for record in records:
            if str(record.get("username", "")).lower() == username:
                try:
                    return int(record.get("telegram_id"))
                except (TypeError, ValueError):
                    return None
        return None

    # ------------------------------------------------------------------
    # Проекты
    # ------------------------------------------------------------------

    def get_project_by_chat_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Ищет проект, привязанный к данному chat_id.

        Args:
            chat_id: ID чата Telegram.

        Returns:
            Словарь с данными проекта (включая row_index) или None.
        """
        records = self.ws_project_info.get_all_records()
        for i, record in enumerate(records, start=2):
            if str(record.get("chat_id")) == str(chat_id):
                record["row_index"] = i
                return record
        return None

    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет проект по точному названию.

        Args:
            name: название проекта.

        Returns:
            Словарь с данными проекта (включая row_index) или None.
        """
        records = self.ws_project_info.get_all_records()
        for i, record in enumerate(records, start=2):
            if str(record.get("Название проекта", "")).strip().lower() == name.strip().lower():
                record["row_index"] = i
                return record
        return None

    def create_project(self, data: Dict[str, Any]) -> str:
        """
        Создаёт новую запись проекта на листе "Инфо о проекте".

        Args:
            data: словарь с ключами, соответствующими PROJECT_INFO_HEADERS
                (кроме "ID", который присваивается автоматически).

        Returns:
            Присвоенный проекту ID (строка).
        """
        records = self.ws_project_info.get_all_records()
        existing_ids = []
        for record in records:
            try:
                existing_ids.append(int(record.get("ID", 0)))
            except (TypeError, ValueError):
                continue
        new_id = str(max(existing_ids) + 1 if existing_ids else 1)

        row = [str(data.get(header, "") if header != "ID" else new_id) for header in PROJECT_INFO_HEADERS]
        self.ws_project_info.append_row(row, value_input_option="USER_ENTERED")
        logger.info("Создан проект '%s' (ID=%s)", data.get("Название проекта"), new_id)
        return new_id

    def update_project_field(self, row_index: int, field: str, value: str) -> None:
        """
        Обновляет одно поле проекта по индексу строки.

        Args:
            row_index: номер строки в листе "Инфо о проекте" (1-based, с заголовком).
            field: название колонки (должно быть в PROJECT_INFO_HEADERS).
            value: новое значение.
        """
        if field not in PROJECT_INFO_HEADERS:
            raise ValueError(f"Неизвестное поле проекта: {field}")
        col_index = PROJECT_INFO_HEADERS.index(field) + 1
        self.ws_project_info.update_cell(row_index, col_index, value)

    # ------------------------------------------------------------------
    # Задачи ("Сверки команды")
    # ------------------------------------------------------------------

    def _next_task_number(self) -> int:
        """Возвращает следующий порядковый номер для новой задачи."""
        records = self.ws_tasks.get_all_records()
        numbers = []
        for record in records:
            try:
                numbers.append(int(record.get("Номер", 0)))
            except (TypeError, ValueError):
                continue
        return max(numbers) + 1 if numbers else 1

    def add_task(self, project_name: str, task_data: Dict[str, str]) -> int:
        """
        Добавляет одну задачу в лист "Сверки команды".

        Args:
            project_name: название проекта.
            task_data: словарь с ключами task_text, executor, deadline.

        Returns:
            Присвоенный задаче номер.
        """
        number = self._next_task_number()
        row = [
            str(number),
            today_str(),
            task_data["task_text"],
            task_data["executor"],
            task_data["deadline"],
            STATUS_IN_PROGRESS,
            project_name,
        ]
        self.ws_tasks.append_row(row, value_input_option="USER_ENTERED")
        return number

    def add_tasks_bulk(self, project_name: str, tasks: List[Dict[str, str]]) -> List[int]:
        """
        Добавляет несколько задач одним пакетным запросом.

        Args:
            project_name: название проекта.
            tasks: список словарей с ключами task_text, executor, deadline.

        Returns:
            Список присвоенных номеров задач (в том же порядке).
        """
        if not tasks:
            return []
        start_number = self._next_task_number()
        rows = []
        numbers = []
        for offset, task in enumerate(tasks):
            number = start_number + offset
            numbers.append(number)
            rows.append([
                str(number),
                today_str(),
                task["task_text"],
                task["executor"],
                task["deadline"],
                STATUS_IN_PROGRESS,
                project_name,
            ])
        self.ws_tasks.append_rows(rows, value_input_option="USER_ENTERED")
        return numbers

    def _get_task_records(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Возвращает все задачи проекта с вычисленным актуальным статусом
        и индексом строки в таблице.

        Args:
            project_name: название проекта.

        Returns:
            Список словарей с ключами Номер, Дата сверки, Задача,
            Исполнитель, Срок выполнения задачи, Статус задачи,
            project_name, row_index.
        """
        records = self.ws_tasks.get_all_records()
        result = []
        for i, record in enumerate(records, start=2):
            if str(record.get("project_name", "")).strip().lower() != project_name.strip().lower():
                continue
            record["row_index"] = i
            record["Статус задачи"] = effective_status(
                str(record.get("Срок выполнения задачи", "")),
                str(record.get("Статус задачи", STATUS_IN_PROGRESS)),
            )
            result.append(record)
        return result

    def get_user_tasks(self, project_name: str, username: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Возвращает задачи конкретного исполнителя в проекте.

        Args:
            project_name: название проекта.
            username: никнейм исполнителя без "@".
            active_only: если True — только незакрытые задачи.

        Returns:
            Список задач, отсортированный по сроку выполнения.
        """
        username = username.lower().lstrip("@")
        tasks = self._get_task_records(project_name)
        tasks = [t for t in tasks if str(t.get("Исполнитель", "")).lower().lstrip("@") == username]
        if active_only:
            tasks = [t for t in tasks if t["Статус задачи"] != STATUS_DONE]
        return self._sort_by_deadline(tasks)

    def get_all_tasks(self, project_name: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Возвращает все задачи проекта.

        Args:
            project_name: название проекта.
            active_only: если True — только незакрытые задачи.

        Returns:
            Список задач, отсортированный по сроку выполнения.
        """
        tasks = self._get_task_records(project_name)
        if active_only:
            tasks = [t for t in tasks if t["Статус задачи"] != STATUS_DONE]
        return self._sort_by_deadline(tasks)

    @staticmethod
    def _sort_by_deadline(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Сортирует список задач по сроку выполнения (от ближайшего)."""
        from datetime import datetime
        from config import DATE_FORMAT

        def key(task):
            try:
                return datetime.strptime(str(task.get("Срок выполнения задачи", "")), DATE_FORMAT)
            except ValueError:
                return datetime.max

        return sorted(tasks, key=key)

    def complete_task(self, project_name: str, task_number: int, username: str) -> Optional[Dict[str, Any]]:
        """
        Отмечает задачу выполненной, если она принадлежит указанному
        пользователю в указанном проекте.

        Args:
            project_name: название проекта.
            task_number: номер задачи (значение колонки "Номер").
            username: никнейм пользователя, вызвавшего команду.

        Returns:
            Словарь с данными задачи, если она найдена и обновлена,
            иначе None.
        """
        username = username.lower().lstrip("@")
        tasks = self._get_task_records(project_name)
        for task in tasks:
            try:
                number_matches = int(task.get("Номер", -1)) == int(task_number)
            except (TypeError, ValueError):
                number_matches = False
            if number_matches and str(task.get("Исполнитель", "")).lower().lstrip("@") == username:
                col_index = TASKS_HEADERS.index("Статус задачи") + 1
                self.ws_tasks.update_cell(task["row_index"], col_index, STATUS_DONE)
                task["Статус задачи"] = STATUS_DONE
                return task
        return None

    def get_task_stats(self, project_name: str) -> Dict[str, int]:
        """
        Считает статистику задач проекта: всего, в работе, просрочено, выполнено.

        Args:
            project_name: название проекта.

        Returns:
            Словарь с ключами total, in_progress, overdue, done.
        """
        tasks = self._get_task_records(project_name)
        stats = {"total": len(tasks), "in_progress": 0, "overdue": 0, "done": 0}
        for task in tasks:
            status = task["Статус задачи"]
            if status == STATUS_DONE:
                stats["done"] += 1
            elif status == "🔴 ПРОСРОЧЕНО":
                stats["overdue"] += 1
            else:
                stats["in_progress"] += 1
        return stats

    # ------------------------------------------------------------------
    # Протоколы
    # ------------------------------------------------------------------

    def add_protocol_entries(self, project_name: str, entries: List[Dict[str, str]]) -> None:
        """
        Добавляет несколько записей корректировок в лист "Протоколы".

        Args:
            project_name: название проекта.
            entries: список словарей с ключами task_text, executor, deadline.
        """
        if not entries:
            return
        rows = []
        for entry in entries:
            rows.append([
                today_str(),
                entry["task_text"],
                entry["executor"],
                entry["deadline"],
                STATUS_IN_PROGRESS,
                project_name,
            ])
        self.ws_protocols.append_rows(rows, value_input_option="USER_ENTERED")
