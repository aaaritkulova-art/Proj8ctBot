"""
Состояния конечных автоматов (FSM) для ConversationHandler'ов бота.

Каждая команда, требующая пошагового ввода данных от пользователя,
использует свой набор состояний. Все состояния — просто целые числа,
уникальные в рамках всего приложения (используем itertools.count,
чтобы избежать случайных коллизий при добавлении новых состояний).
"""
import itertools

_counter = itertools.count()

# /новыйпроект
WAITING_PROJECT_NAME = next(_counter)
WAITING_MANAGER = next(_counter)
WAITING_DATES = next(_counter)
WAITING_MEMBERS_ARCHITECTS = next(_counter)
WAITING_MEMBERS_DESIGNERS = next(_counter)
WAITING_MEMBERS_PARTNERS = next(_counter)
WAITING_LINKS_GDRIVE = next(_counter)
WAITING_LINKS_YANDEX = next(_counter)
WAITING_LINKS_MIRO = next(_counter)

# /сверка
WAITING_TASKS_LIST = next(_counter)

# /протокол
WAITING_PROTOCOL_LIST = next(_counter)

# /выполнил
WAITING_TASK_NUMBER = next(_counter)
