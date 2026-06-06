"""
utils/modbus_map.py

Карта Modbus-регистров для HMI HVoF.

Важно:
- В коде используются реальные адреса Modbus PDU, то есть 0-based.
- Если в документации МК пишут 40001, в коде это адрес 0.
- Значения параметров передаются как целые числа с масштабом x10:
      35.5 -> 355
      120.0 -> 1200
"""

from utils.constants import INSTALL_WIRE, INSTALL_POWDER


# ─────────────────────────────────────────────────────────────
# Общие настройки Modbus RTU
# ─────────────────────────────────────────────────────────────

MODBUS_SLAVE_ID = 1
MODBUS_VALUE_SCALE = 10.0

# Период основного опроса МК, мс.
MODBUS_POLL_INTERVAL_MS = 500

# Таймаут отсутствия успешного обмена, мс.
MODBUS_LINK_TIMEOUT_MS = 3000

# Как часто читать уставки и команды из МК.
# 10 * 500 мс = 5 секунд.
MODBUS_SLOW_POLL_EVERY = 10


# ─────────────────────────────────────────────────────────────
# Параметры установки
# ─────────────────────────────────────────────────────────────

PARAM_INDEX = {
    "propane": 0,
    "oxygen": 1,
    "air": 2,
    "feeder": 3,
    "pistol": 4,
}

PARAM_ORDER = (
    "propane",
    "oxygen",
    "air",
    "feeder",
    "pistol",
)


# ─────────────────────────────────────────────────────────────
# Holding registers: HMI -> МК
# ─────────────────────────────────────────────────────────────

# Уставки.
SETPOINT_BASE = {
    INSTALL_WIRE: 0,       # 40001..40005
    INSTALL_POWDER: 10,    # 40011..40015
}

# Команды одной битовой маской.
COMMAND_REGISTER = {
    INSTALL_WIRE: 20,      # 40021
    INSTALL_POWDER: 21,    # 40022
}


# ─────────────────────────────────────────────────────────────
# Holding/Input registers: МК -> HMI
# ─────────────────────────────────────────────────────────────

# Текущие значения.
CURRENT_BASE = {
    INSTALL_WIRE: 100,     # 40101..40105 или 30101..30105
    INSTALL_POWDER: 110,   # 40111..40115 или 30111..30115
}

# Маски аварий.
ERROR_REGISTER = {
    INSTALL_WIRE: 120,     # 40121 или 30121
    INSTALL_POWDER: 121,   # 40122 или 30122
}


# ─────────────────────────────────────────────────────────────
# Биты команд
# ─────────────────────────────────────────────────────────────

COMMAND_BITS = {
    "main_system": 0,
    "ignition": 1,
    "feeding_system": 2,
    "propane_valve": 3,
    "oxygen_valve": 4,
    "air_valve": 5,
    "feeder_motor": 6,
    "pistol_motor": 7,
}

COMMAND_BY_BIT = {
    bit: command
    for command, bit in COMMAND_BITS.items()
}


# ─────────────────────────────────────────────────────────────
# Биты аварий
# ─────────────────────────────────────────────────────────────

ERROR_BITS = {
    "propane_fault": 0,
    "oxygen_fault": 1,
    "air_fault": 2,
    "feeder_fault": 3,
    "pistol_fault": 4,
    "general_fault": 5,
}

ERROR_MESSAGES = {
    "propane_fault": "Авария пропана",
    "oxygen_fault": "Авария кислорода",
    "air_fault": "Авария воздуха",
    "feeder_fault": "Авария подачи",
    "pistol_fault": "Авария пистолета/патателя",
    "general_fault": "Общая авария установки",
}


def scale_to_register(value: float) -> int:
    """
    Преобразует значение HMI в uint16 Modbus-регистр.

    Пример:
        35.5 -> 355
        120.0 -> 1200

    Значение ограничивается диапазоном uint16:
        0..65535
    """
    raw = int(round(float(value) * MODBUS_VALUE_SCALE))

    if raw < 0:
        raw = 0

    if raw > 0xFFFF:
        raw = 0xFFFF

    return raw


def would_clip_register(value: float) -> bool:
    """
    Проверяет, будет ли значение обрезано при преобразовании в uint16.
    """
    raw = int(round(float(value) * MODBUS_VALUE_SCALE))
    return raw < 0 or raw > 0xFFFF


def register_to_float(value: int) -> float:
    """
    Преобразует uint16 Modbus-регистр в значение HMI.

    Пример:
        355 -> 35.5
        1200 -> 120.0
    """
    return round(int(value) / MODBUS_VALUE_SCALE, 2)


def setpoint_address(install: str, param: str) -> int:
    """
    Возвращает адрес регистра уставки.
    """
    return SETPOINT_BASE[install] + PARAM_INDEX[param]


def current_address(install: str, param: str) -> int:
    """
    Возвращает адрес регистра текущего значения.
    """
    return CURRENT_BASE[install] + PARAM_INDEX[param]


def command_mask_set(mask: int, command: str, enabled: bool) -> int:
    """
    Устанавливает или сбрасывает бит команды в маске.
    """
    bit = COMMAND_BITS[command]

    if enabled:
        return int(mask) | (1 << bit)

    return int(mask) & ~(1 << bit)


def command_mask_to_states(mask: int) -> dict[str, bool]:
    """
    Преобразует командную маску в словарь:
        command_name -> bool
    """
    return {
        command: bool(int(mask) & (1 << bit))
        for command, bit in COMMAND_BITS.items()
    }


def error_mask_to_message(mask: int) -> tuple[bool, str]:
    """
    Преобразует маску аварий в:
        has_error: bool
        message: str
    """
    messages = []

    for error_name, bit in ERROR_BITS.items():
        if int(mask) & (1 << bit):
            messages.append(ERROR_MESSAGES.get(error_name, error_name))

    if not messages:
        return False, ""

    return True, "; ".join(messages)
