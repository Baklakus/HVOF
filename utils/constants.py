"""
utils/constants.py

Общие константы проекта HMI HVoF.
Файл не импортирует PyQt6 и не содержит UI-логики.
"""

# ─────────────────────────────────────────────────────────────
# UART / COM-порт
# ─────────────────────────────────────────────────────────────

SERIAL_PORT = "COM10"
SERIAL_BAUD = 115200
SERIAL_TIMEOUT_SEC = 0.0
UART_POLL_INTERVAL_MS = 50
UART_LINK_TIMEOUT_MS = 3000

# ─────────────────────────────────────────────────────────────
# Файлы данных
# ─────────────────────────────────────────────────────────────

RECIPES_FILE = "recipes.json"
STARTUP_PARAMS_FILE = "startup_params.json"

# ─────────────────────────────────────────────────────────────
# Типы установок
# ─────────────────────────────────────────────────────────────

INSTALL_WIRE = "wire"
INSTALL_POWDER = "powder"
INSTALL_TYPES = (INSTALL_WIRE, INSTALL_POWDER)
INSTALL_TITLES = {
    INSTALL_WIRE: "ПРОВОЛОКА",
    INSTALL_POWDER: "ПОРОШОК",
}

# ─────────────────────────────────────────────────────────────
# Параметры рабочего экрана
# ─────────────────────────────────────────────────────────────

PARAM_NAMES = ("propane", "oxygen", "air", "feeder", "pistol")
PARAM_TITLES = {
    "propane": "Пропан",
    "oxygen": "Кислород",
    "air": "Воздух",
    "feeder": "Подача / Q газа",
    "pistol": "Пистолет / Пататель",
}

DEFAULT_SETPOINTS = {
    INSTALL_WIRE: {
        "propane": 35.0,
        "oxygen": 120.0,
        "air": 250.0,
        "feeder": 80.0,
        "pistol": 60.0,
    },
    INSTALL_POWDER: {
        "propane": 45.0,
        "oxygen": 160.0,
        "air": 310.0,
        "feeder": 45.0,
        "pistol": 0.0,
    },
}



PARAM_NAMES = (
    "propane",
    "oxygen",
    "air",
    "feeder",
    "pistol",
)


DEFAULT_STARTUP_PARAMS = {
    INSTALL_WIRE: {
        "propane": 20.0,
        "oxygen": 80.0,
        "air": 150.0,
        "feeder": 20.0,
        "pistol": 20.0,
        "ignition_delay": 2.0,
        "feeding_delay": 3.0,
    },
    INSTALL_POWDER: {
        "propane": 25.0,
        "oxygen": 90.0,
        "air": 180.0,
        "feeder": 10.0,
        "pistol": 0.0,
        "ignition_delay": 2.0,
        "feeding_delay": 4.0,
    },
}


STARTUP_PARAM_TITLES = {
    "propane": "Пропан запуска",
    "oxygen": "Кислород запуска",
    "air": "Воздух запуска",
    "feeder": "Подача запуска",
    "pistol": "Пистолет / Пататель запуска",
    "ignition_delay": "Задержка поджига",
    "feeding_delay": "Задержка подачи",
}


STARTUP_PARAM_UNITS = {
    "propane": "л/мин",
    "oxygen": "л/мин",
    "air": "л/мин",
    "feeder": "об/мин / г/мин",
    "pistol": "об/мин",
    "ignition_delay": "сек",
    "feeding_delay": "сек",
}



DEFAULT_CURRENT_VALUES = {
    INSTALL_WIRE: {name: 0.0 for name in PARAM_NAMES},
    INSTALL_POWDER: {name: 0.0 for name in PARAM_NAMES},
}

SETPOINT_STEPS = {
    "propane": 0.5,
    "oxygen": 2.0,
    "air": 5.0,
    "feeder": 1.0,
    "pistol": 1.0,
}

NODE_NAMES = PARAM_NAMES
DEFAULT_NODE_STATES = {name: False for name in NODE_NAMES}

# ─────────────────────────────────────────────────────────────
# Рецепты / рабочие режимы
# Номер режима хранит сама таблица Qt через вертикальный заголовок.
# В JSON номер не записывается.
# ─────────────────────────────────────────────────────────────

RECIPE_COLUMNS = (
    "material",
    "diameter",
    "gas_ratio",
    "propane",
    "oxygen",
    "air",
    "feeder_speed",
    "pistol_speed",
)

RECIPE_HEADERS = (
    "Материал",
    "Диаметр",
    "Соотношение газов",
    "Пропан",
    "Кислород",
    "Воздух",
    "Скорость подачи",
    "Пистолет/Пататель",
)

RECIPE_NUMERIC_COLUMNS = (1, 3, 4, 5, 6, 7)

DEFAULT_RECIPES = {
    INSTALL_WIRE: [
        {
            "material": "Проволока",
            "diameter": 1.6,
            "gas_ratio": "30/100/220",
            "propane": 30.0,
            "oxygen": 100.0,
            "air": 220.0,
            "feeder_speed": 70.0,
            "pistol_speed": 60.0,
        },
        {
            "material": "Проволока",
            "diameter": 2.0,
            "gas_ratio": "35/120/250",
            "propane": 35.0,
            "oxygen": 120.0,
            "air": 250.0,
            "feeder_speed": 80.0,
            "pistol_speed": 60.0,
        },
        {
            "material": "Проволока",
            "diameter": 2.4,
            "gas_ratio": "40/140/280",
            "propane": 40.0,
            "oxygen": 140.0,
            "air": 280.0,
            "feeder_speed": 90.0,
            "pistol_speed": 60.0,
        },
    ],
    INSTALL_POWDER: [
        {
            "material": "NiCr",
            "diameter": 0.0,
            "gas_ratio": "45/150/300",
            "propane": 45.0,
            "oxygen": 150.0,
            "air": 300.0,
            "feeder_speed": 25.0,
            "pistol_speed": 0.0,
        },
        {
            "material": "WC-Co",
            "diameter": 0.0,
            "gas_ratio": "50/170/320",
            "propane": 50.0,
            "oxygen": 170.0,
            "air": 320.0,
            "feeder_speed": 32.0,
            "pistol_speed": 0.0,
        },
        {
            "material": "Cr₃C₂",
            "diameter": 0.0,
            "gas_ratio": "55/190/340",
            "propane": 55.0,
            "oxygen": 190.0,
            "air": 340.0,
            "feeder_speed": 38.0,
            "pistol_speed": 0.0,
        },
    ],
}

# ─────────────────────────────────────────────────────────────
# Параметры запуска установки
# Значения можно уточнить под реальный технологический регламент.
# ─────────────────────────────────────────────────────────────

STARTUP_PARAM_COLUMNS = (
    "propane",
    "oxygen",
    "air",
    "feeder",
    "pistol",
    "ignition_delay",
    "feeding_delay",
)

STARTUP_PARAM_TITLES = {
    "propane": "Пропан запуска, л/мин",
    "oxygen": "Кислород запуска, л/мин",
    "air": "Воздух запуска, л/мин",
    "feeder": "Подача запуска",
    "pistol": "Пистолет/Питатель запуска",
    "ignition_delay": "Задержка поджига, с",
    "feeding_delay": "Задержка подачи, с",
}

DEFAULT_STARTUP_PARAMS = {
    INSTALL_WIRE: {
        "propane": 25.0,
        "oxygen": 80.0,
        "air": 180.0,
        "feeder": 30.0,
        "pistol": 30.0,
        "ignition_delay": 1.0,
        "feeding_delay": 2.0,
    },
    INSTALL_POWDER: {
        "propane": 35.0,
        "oxygen": 120.0,
        "air": 240.0,
        "feeder": 10.0,
        "pistol": 0.0,
        "ignition_delay": 1.0,
        "feeding_delay": 2.5,
    },
}
