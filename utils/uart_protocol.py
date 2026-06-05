import struct

from utils.constants import INSTALL_WIRE, INSTALL_POWDER

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
PARAM_NAME_TO_CODE = {value: key for key, value in PARAM_CODE_TO_NAME.items()}

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
COMMAND_CODE_TO_NAME = {value: key for key, value in COMMAND_NAME_TO_CODE.items()}

ERROR_CODE_TO_NAME = {
    0x80: "propane_fault",
    0x81: "oxygen_fault",
    0x82: "air_fault",
    0x83: "feeder_fault",
    0x84: "pistol_fault",
    0x90: "general_fault",
    0x91: "fault_clear",
}
ERROR_NAME_TO_CODE = {value: key for key, value in ERROR_CODE_TO_NAME.items()}
ERROR_MESSAGES = {
    "propane_fault": "Авария пропана",
    "oxygen_fault": "Авария кислорода",
    "air_fault": "Авария воздуха",
    "feeder_fault": "Авария подачи",
    "pistol_fault": "Авария пистолета/питателя",
    "general_fault": "Общая авария установки",
    "fault_clear": "Авария сброшена",
}


class UartProtocolError(ValueError):
    pass


def crc16_int(data: bytes) -> int:
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
    return data + struct.pack(">H", crc16_int(data))


def check_crc(packet: bytes) -> bool:
    if len(packet) < 3:
        return False
    received_crc = struct.unpack(">H", packet[-2:])[0]
    calculated_crc = crc16_int(packet[:-2])
    return calculated_crc == received_crc


def make_float_packet(install: str, code: int, value: float) -> bytes:
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
    if param_name not in PARAM_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестный параметр: {param_name}")
    return make_float_packet(install, PARAM_NAME_TO_CODE[param_name], value)


def make_command_packet(install: str, command_name: str, state: bool) -> bytes:
    if command_name not in COMMAND_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестная команда: {command_name}")
    return make_float_packet(install, COMMAND_NAME_TO_CODE[command_name], 1.0 if state else 0.0)


def make_error_packet(install: str, error_name: str, active: bool = True) -> bytes:
    if error_name not in ERROR_NAME_TO_CODE:
        raise UartProtocolError(f"Неизвестная ошибка: {error_name}")
    return make_float_packet(install, ERROR_NAME_TO_CODE[error_name], 1.0 if active else 0.0)


def parse_float_packet(packet: bytes) -> tuple[str, int, float]:
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
    install, code, value = parse_float_packet(packet)
    param_name = PARAM_CODE_TO_NAME.get(code)
    if param_name is None:
        raise UartProtocolError(f"Неизвестный код параметра: 0x{code:02X}")
    return install, param_name, value


def parse_command_packet(packet: bytes) -> tuple[str, str, bool]:
    install, code, value = parse_float_packet(packet)
    command_name = COMMAND_CODE_TO_NAME.get(code)
    if command_name is None:
        raise UartProtocolError(f"Неизвестный код команды: 0x{code:02X}")
    return install, command_name, value >= 1.0


def parse_error_packet(packet: bytes) -> tuple[str, bool, str, str]:
    install, code, value = parse_float_packet(packet)
    error_name = ERROR_CODE_TO_NAME.get(code)
    if error_name is None:
        raise UartProtocolError(f"Неизвестный код ошибки: 0x{code:02X}")

    if error_name == "fault_clear":
        return install, False, "", error_name

    active = value >= 1.0
    return install, active, ERROR_MESSAGES.get(error_name, error_name), error_name


def classify_packet_code(code: int) -> str:
    if code in PARAM_CODE_TO_NAME:
        return "current"
    if code in ERROR_CODE_TO_NAME:
        return "error"
    if code in COMMAND_CODE_TO_NAME:
        return "command"
    return "unknown"


def packet_to_hex(packet: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in packet)


def find_packet_in_buffer(buffer: bytearray) -> bytes | None:
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
