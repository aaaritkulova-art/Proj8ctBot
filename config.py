"""
Конфигурация проекта.

Загружает переменные окружения из .env и делает их доступными
для остальных модулей приложения.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# Есть два способа передать сервисный ключ Google:
# 1. GOOGLE_CREDENTIALS_FILE — путь к JSON-файлу на диске (удобно локально).
# 2. GOOGLE_CREDENTIALS_JSON — содержимое JSON-файла целиком, одной строкой
#    (нужно на хостингах без файлового доступа, например Railway — там
#    секрет кладётся как переменная окружения, а не как файл).
# Если задано GOOGLE_CREDENTIALS_JSON, оно имеет приоритет.
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# Названия листов Google Таблицы
SHEET_PROJECT_INFO = "Инфо о проекте"
SHEET_TASKS = "Сверки команды"
SHEET_PROTOCOLS = "Протоколы"

# Статусы задач
STATUS_IN_PROGRESS = "⏳ В работе"
STATUS_OVERDUE = "🔴 ПРОСРОЧЕНО"
STATUS_DONE = "✅ Выполнено"

ACTIVE_STATUSES = (STATUS_IN_PROGRESS, STATUS_OVERDUE)

# Формат дат, используемый во всём проекте
DATE_FORMAT = "%d.%m.%Y"


def validate_config() -> None:
    """
    Проверяет, что все обязательные переменные окружения заданы.

    Raises:
        RuntimeError: если какая-то из обязательных переменных отсутствует.
    """
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if not GOOGLE_CREDENTIALS_JSON and not (GOOGLE_CREDENTIALS_FILE and os.path.exists(GOOGLE_CREDENTIALS_FILE)):
        missing.append("GOOGLE_CREDENTIALS_JSON (или файл по пути GOOGLE_CREDENTIALS_FILE)")
    if missing:
        raise RuntimeError(
            f"Не заданы обязательные переменные окружения: {', '.join(missing)}. "
            f"Проверьте файл .env (см. .env.example)."
        )


def setup_logging() -> None:
    """Настраивает базовое логирование для всего приложения."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Снижаем шум от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("gspread").setLevel(logging.WARNING)
