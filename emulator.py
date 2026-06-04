"""
emulator.py — COM-порт эмулятор для HMI HVoF
============================================

Схема для Windows + com0com:
    main.py    -> COM10
    emulator   -> COM11

Запускать отдельно:
    python emulator.py

Что делает эмулятор:
- принимает уставки и команды от HMI;
- хранит отдельное состояние для ПРОВОЛОКИ и ПОРОШКА;
- плавно подтягивает текущие значения к последним уставкам;
- каждые 1 секунду отправляет текущие значения обратно в HMI.
"""

import random
import struct
import threading
import time

import serial


PORT_NAME = "COM11"
BAUD_RATE = 115200
PACKET_LEN = 9  # AA(1) + inst(1) + param/cmd(1) + float(4) + CRC16(2)
SEND_PERIOD_SEC = 1.0

INSTALL_WIRE = ord("W")
INSTALL_POWDER = ord("P")
INSTALLS = (INSTALL_WIRE, INSTALL_POWDER)

INSTALL_NAMES = {
    INSTALL_WIRE: "ПРОВОЛОКА",
    INSTALL_POWDER: "ПОРОШОК",
}

PARAM_NAMES = {
    0x01: "Пропан",
    0x02: "Кислород",
    0x03: "Воздух",
    0x04: "Подача/Q газа",
    0x05: "Пистолет/Питатель",
}

CMD_NAMES = {
    0x10: "СИСТЕМА",
    0x11: "ЗАЖИГАНИЕ ДУГИ",
    0x12: "СИСТЕМА ПОДАЧИ",
    0x20: "Клапан Пропан",
    0x21: "Клапан Кислород",
    0x22: "Клапан Воздух",
    0x23: "Мотор подачи",
    0x24: "Мотор пистолета",
}

DEFAULT_TARGETS = {
    INSTALL_WIRE: {
        0x01: 35.0,
        0x02: 120.0,
        0x03: 250.0,
        0x04: 80.0,
        0x05: 60.0,
    },
    INSTALL_POWDER: {
        0x01: 45.0,
        0x02: 160.0,
        0x03: 310.0,
        0x04: 45.0,
        0x05: 0.0,
    },
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF

    for b in data:
        crc ^= b

        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc


def check_crc(pkt: bytes) -> bool:
    if len(pkt) < 3:
        return False

    return crc16(pkt[:-2]) == struct.unpack(">H", pkt[-2:])[0]


def make_packet(inst: int, param: int, value: float) -> bytes:
    body = struct.pack(">BBBf", 0xAA, inst, param, float(value))
    return body + struct.pack(">H", crc16(body))


class EmulatorState:
    def __init__(self):
        self.lock = threading.Lock()

        self.targets = {
            inst: values.copy()
            for inst, values in DEFAULT_TARGETS.items()
        }

        self.current = {
            inst: values.copy()
            for inst, values in DEFAULT_TARGETS.items()
        }

        self.commands = {
            inst: {}
            for inst in INSTALLS
        }

    def set_target(self, inst: int, param: int, value: float):
        with self.lock:
            if inst in self.targets and param in self.targets[inst]:
                self.targets[inst][param] = float(value)

    def set_command(self, inst: int, cmd: int, state: bool):
        with self.lock:
            if inst in self.commands:
                self.commands[inst][cmd] = state

    def tick_current_values(self):
        """
        Плавно двигает текущие значения к уставкам.
        Это имитирует физическую систему: текущее значение не меняется мгновенно.
        """
        with self.lock:
            for inst in INSTALLS:
                for param, target in self.targets[inst].items():
                    cur = self.current[inst][param]
                    delta = target - cur

                    cur += delta * 0.25
                    cur += random.uniform(-0.15, 0.15)

                    if cur < 0:
                        cur = 0.0

                    self.current[inst][param] = cur

    def snapshot_current(self):
        with self.lock:
            return {
                inst: values.copy()
                for inst, values in self.current.items()
            }


def decode_and_apply_packet(raw: bytes, state: EmulatorState) -> str:
    hex_str = " ".join(f"{b:02X}" for b in raw)

    if len(raw) != PACKET_LEN:
        return f"  [!] Неверная длина {len(raw)} байт | {hex_str}"

    if raw[0] != 0xAA:
        return f"  [!] Нет старт-байта 0xAA | {hex_str}"

    if not check_crc(raw):
        return f"  [!] ОШИБКА CRC | {hex_str}"

    inst = raw[1]
    code = raw[2]
    value = struct.unpack(">f", raw[3:7])[0]

    inst_name = INSTALL_NAMES.get(inst, f"0x{inst:02X}")

    if code in PARAM_NAMES:
        state.set_target(inst, code, value)

        return (
            f"  [OK] УСТАВКА  | {inst_name:10s} | "
            f"{PARAM_NAMES[code]:18s} | цель = {value:8.2f}"
        )

    if code in CMD_NAMES:
        enabled = value >= 1.0
        state.set_command(inst, code, enabled)

        return (
            f"  [OK] КОМАНДА  | {inst_name:10s} | "
            f"{CMD_NAMES[code]:18s} | {'ВКЛ' if enabled else 'ВЫКЛ'}"
        )

    return f"  [?] Неизвестный код 0x{code:02X} | val={value:.2f} | {hex_str}"


def receiver_loop(port: serial.Serial, state: EmulatorState, stop: threading.Event):
    buf = bytearray()

    print(f"  Слушаю {port.name} @ {port.baudrate} baud...\n")

    while not stop.is_set():
        try:
            chunk = port.read(port.in_waiting or 1)
        except serial.SerialException as e:
            print(f"  [!] Ошибка порта: {e}")
            break

        if not chunk:
            continue

        buf.extend(chunk)

        while True:
            idx = buf.find(0xAA)

            if idx == -1:
                buf.clear()
                break

            if idx > 0:
                print(f"  [~] Пропуск {idx} мусорных байт")
                del buf[:idx]

            if len(buf) < PACKET_LEN:
                break

            pkt = bytes(buf[:PACKET_LEN])
            del buf[:PACKET_LEN]

            print(decode_and_apply_packet(pkt, state), flush=True)


def telemetry_loop(port: serial.Serial, state: EmulatorState, stop: threading.Event):
    print(f"  Передача текущих параметров запущена: период {SEND_PERIOD_SEC:.1f} сек\n")

    while not stop.is_set():
        state.tick_current_values()
        snapshot = state.snapshot_current()

        for inst in INSTALLS:
            for param, value in snapshot[inst].items():
                pkt = make_packet(inst, param, value)

                try:
                    port.write(pkt)
                except serial.SerialException as e:
                    print(f"  [!] Ошибка отправки телеметрии: {e}")
                    return

        time.sleep(SEND_PERIOD_SEC)


def main():
    print("=" * 64)
    print("  HVoF UART Эмулятор с передачей текущих параметров")
    print(f"  Порт: {PORT_NAME} | Baud: {BAUD_RATE}")
    print("  Ctrl+C — выход")
    print("=" * 64)

    try:
        port = serial.Serial(
            port=PORT_NAME,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
        )
    except serial.SerialException as e:
        print(f"\n  [ОШИБКА] Не удалось открыть {PORT_NAME}: {e}")
        print("\n  Проверь:")
        print("  1. com0com установлен и пара COM10/COM11 создана")
        print("  2. Порт не занят другой программой")
        print("  3. В диспетчере устройств виден COM11")
        return

    print(f"\n  Порт {PORT_NAME} открыт успешно. Жду пакетов от main.py...\n")

    state = EmulatorState()
    stop = threading.Event()

    t_rx = threading.Thread(
        target=receiver_loop,
        args=(port, state, stop),
        daemon=True,
    )

    t_tx = threading.Thread(
        target=telemetry_loop,
        args=(port, state, stop),
        daemon=True,
    )

    t_rx.start()
    t_tx.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  Завершение...")
    finally:
        stop.set()
        port.close()


if __name__ == "__main__":
    main()