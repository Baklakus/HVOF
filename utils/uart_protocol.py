import struct

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_POWDER,
)


PACKET_LEN = 9

START_BYTE = 0xAA

INSTALL_NAME_TO_CODE = {
    INSTALL_WIRE: ord("W"),
    INSTALL_POWDER: ord("P"),
}

INSTALL_CODE_TO_NAME = {
    ord("W"): INSTALL_WIRE,
    ord("P"): INSTALL_POWDER,
}

PARAM_CODE_TO_NAME = {
    0x01: "propane",
    0x02: "oxygen",
    0x03: "air",
    0x04: "feeder",
    0x05: "pistol",
}

PARAM_NAME_TO_CODE = {
    value: key for key, value in PARAM_CODE_TO_NAME.items()
}

COMMAND_NAME_TO_CODE = {
    "main_system": 0x10,
    "ignition": 0x11,
    "feeding_system": 0x12,
    "propane_valve": 0x20,
    "oxygen_valve": 0x21,
    "air_valve": 0x22,
    "feeder_motor": 0x23,
    "pistol_motor": 0x24,
}

COMMAND_CODE_TO_NAME = {
    value: key for key, value in COMMAND_NAME_TO_CODE.items()
}


class UartProtocolError(ValueError):
    pass


def crc16_int(data: bytes) -> int:
    """
    CRC-16 Modbus.
    Используется для проверки пакетов HMI <-> МК/эмулятор.
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc


def append_crc(data: bytes) -> bytes:
    """
    Добавляет CRC16 к телу пакета.
    CRC пишется в big-endian формате, как было в текущем main.py/emulator.py.
    """
    return data + struct.pack(">H", crc16_int(data))


def check_crc(packet: bytes) -> bool:
    """
    Проверяет CRC входящего пакета.
    """
    if len(packet) < 3:
        return False

    received_crc = struct.unpack(">H", packet[-2:])[0]
    calculated_crc = crc16_int(packet[:-2])

    return calculated_crc == received_crc


def make_float_packet(install: str, code: int, value: float) -> bytes:
    """
    Собирает пакет формата:

    AA + install + param_or_command + float + CRC16

    install:
        "wire" или "powder"

    code:
        код параметра или команды

    value:
        float-значение.
        Для команд используется 1.0 / 0.0.
    """
    if install not in INSTALL_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестная установка: {install}")

    body = struct.pack(
        ">BBBf",
        START_BYTE,
        INSTALL_NAME_TO_CODE[install],
        int(code),
        float(value),
    )

    return append_crc(body)


def make_setpoint_packet(install: str, param_name: str, value: float) -> bytes:
    """
    Собирает пакет уставки по имени параметра.
    """
    if param_name not in PARAM_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестный параметр: {param_name}")

    return make_float_packet(
        install=install,
        code=PARAM_NAME_TO_CODE[param_name],
        value=value,
    )


def make_command_packet(install: str, command_name: str, state: bool) -> bytes:
    """
    Собирает пакет команды по имени команды.
    """
    if command_name not in COMMAND_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестная команда: {command_name}")

    return make_float_packet(
        install=install,
        code=COMMAND_NAME_TO_CODE[command_name],
        value=1.0 if state else 0.0,
    )


def parse_float_packet(packet: bytes) -> tuple[str, int, float]:
    """
    Разбирает сырой пакет и возвращает:

    install, code, value

    install:
        "wire" или "powder"

    code:
        код параметра или команды

    value:
        float-значение
    """
    if len(packet) != PACKET_LEN:
        raise UartProtocolError(
            f"Неверная длина пакета: {len(packet)} байт, ожидается {PACKET_LEN}"
        )

    if packet[0] != START_BYTE:
        raise UartProtocolError("Неверный старт-байт пакета")

    if not check_crc(packet):
        raise UartProtocolError("Ошибка CRC пакета")

    install_code = packet[1]
    code = packet[2]
    value = struct.unpack(">f", packet[3:7])[0]

    install = INSTALL_CODE_TO_NAME.get(install_code)

    if install is None:
        raise UartProtocolError(f"Неизвестный код установки: 0x{install_code:02X}")

    return install, code, value


def parse_current_value_packet(packet: bytes) -> tuple[str, str, float]:
    """
    Разбирает пакет текущего значения от МК/эмулятора.

    Возвращает:

    install, param_name, value
    """
    install, code, value = parse_float_packet(packet)

    param_name = PARAM_CODE_TO_NAME.get(code)

    if param_name is None:
        raise UartProtocolError(f"Неизвестный код параметра: 0x{code:02X}")

    return install, param_name, value


def parse_command_packet(packet: bytes) -> tuple[str, str, bool]:
    """
    Разбирает пакет команды, если понадобится принимать команды обратно.
    Сейчас основное приложение в первую очередь принимает текущие значения,
    но функция полезна для тестов и расширения протокола.
    """
    install, code, value = parse_float_packet(packet)

    command_name = COMMAND_CODE_TO_NAME.get(code)

    if command_name is None:
        raise UartProtocolError(f"Неизвестный код команды: 0x{code:02X}")

    return install, command_name, value >= 1.0


def packet_to_hex(packet: bytes) -> str:
    """
    Удобный вывод пакета в HEX для логов.
    """
    return " ".join(f"{byte:02X}" for byte in packet)


def find_packet_in_buffer(buffer: bytearray) -> bytes | None:
    """
    Ищет один полный пакет в буфере UART.

    Возвращает bytes, если пакет найден.
    Возвращает None, если полного пакета пока нет.

    Мусор до старт-байта 0xAA удаляется.
    """
    while True:
        start_index = buffer.find(START_BYTE)

        if start_index < 0:
            buffer.clear()
            return None

        if start_index > 0:
            del buffer[:start_index]

        if len(buffer) < PACKET_LEN:
            return None

        packet = bytes(buffer[:PACKET_LEN])
        del buffer[:PACKET_LEN]

        return packet

