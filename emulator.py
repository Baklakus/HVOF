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
- плавно подтягивает текущие значения к уставкам;
- учитывает включение/выключение системы и узлов;
- каждые 1 секунду отправляет текущие значения обратно в HMI;
- позволяет вручную симулировать аварии из консоли.
"""

import random
import struct
import threading
import time

import serial


PORT_NAME = "COM11"
BAUD_RATE = 115200
PACKET_LEN = 9
SEND_PERIOD_SEC = 1.0
START_BYTE = 0xAA

INSTALL_WIRE = ord("W")
INSTALL_POWDER = ord("P")
INSTALLS = (INSTALL_WIRE, INSTALL_POWDER)

INSTALL_ALIASES = {
    "wire": INSTALL_WIRE,
    "w": INSTALL_WIRE,
    "проволока": INSTALL_WIRE,
    "powder": INSTALL_POWDER,
    "p": INSTALL_POWDER,
    "порошок": INSTALL_POWDER,
}

INSTALL_NAMES = {
    INSTALL_WIRE: "ПРОВОЛОКА",
    INSTALL_POWDER: "ПОРОШОК",
}

PARAM_NAMES = {
    0x01: "Пропан",
    0x02: "Кислород",
    0x03: "Воздух",
    0x04: "Подача/Q газа",
    0x05: "Пистолет/Пататель",
}

CMD_NAMES = {
    0x10: "СИСТЕМА",
    0x11: "ЗАЖИГАНИЕ ДУГИ",
    0x12: "СИСТЕМА ПОДАЧИ",
    0x20: "Клапан Пропан",
    0x21: "Клапан Кислород",
    0x22: "Клапан Воздух",
    0x23: "Мотор подачи",
    0x24: "Мотор пистолета/патателя",
}

PARAM_REQUIRED_CMD = {
    0x01: 0x20,
    0x02: 0x21,
    0x03: 0x22,
    0x04: 0x23,
    0x05: 0x24,
}

ERROR_CODES = {
    "propane": 0x80,
    "oxygen": 0x81,
    "air": 0x82,
    "feeder": 0x83,
    "pistol": 0x84,
    "general": 0x90,
    "clear": 0x91,
}

ERROR_NAMES = {
    0x80: "Авария пропана",
    0x81: "Авария кислорода",
    0x82: "Авария воздуха",
    0x83: "Авария подачи",
    0x84: "Авария пистолета/патателя",
    0x90: "Общая авария",
    0x91: "Сброс аварии",
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


def make_packet(inst: int, code: int, value: float) -> bytes:
    body = struct.pack(">BBBf", START_BYTE, inst, code, float(value))
    return body + struct.pack(">H", crc16(body))


def packet_to_hex(packet: bytes) -> str:
    return " ".join(f"{b:02X}" for b in packet)


class EmulatorState:
    def __init__(self):
        self.lock = threading.Lock()
        self.targets = {inst: values.copy() for inst, values in DEFAULT_TARGETS.items()}
        self.current = {
            inst: {param: 0.0 for param in values}
            for inst, values in DEFAULT_TARGETS.items()
        }
        self.commands = {
            inst: {
                0x10: False,
                0x11: False,
                0x12: False,
                0x20: False,
                0x21: False,
                0x22: False,
                0x23: False,
                0x24: False,
            }
            for inst in INSTALLS
        }
        self.active_faults = {inst: set() for inst in INSTALLS}
        self.telemetry_enabled = True

    def set_target(self, inst: int, param: int, value: float):
        with self.lock:
            if inst in self.targets and param in self.targets[inst]:
                self.targets[inst][param] = float(value)

    def set_command(self, inst: int, cmd: int, state: bool):
        with self.lock:
            if inst in self.commands:
                self.commands[inst][cmd] = bool(state)
                if cmd == 0x10 and not state:
                    for code in self.commands[inst]:
                        self.commands[inst][code] = False

    def set_fault(self, inst: int, fault_name: str, active: bool):
        with self.lock:
            if inst not in self.active_faults:
                return
            if active:
                self.active_faults[inst].add(fault_name)
            else:
                self.active_faults[inst].discard(fault_name)

    def clear_faults(self, inst: int | None = None):
        with self.lock:
            if inst is None:
                for key in self.active_faults:
                    self.active_faults[key].clear()
            elif inst in self.active_faults:
                self.active_faults[inst].clear()

    def set_telemetry(self, enabled: bool):
        with self.lock:
            self.telemetry_enabled = bool(enabled)

    def is_telemetry_enabled(self) -> bool:
        with self.lock:
            return self.telemetry_enabled

    def tick_current_values(self):
        with self.lock:
            for inst in INSTALLS:
                system_on = self.commands[inst].get(0x10, False)
                for param, target in self.targets[inst].items():
                    required_cmd = PARAM_REQUIRED_CMD.get(param)
                    node_on = self.commands[inst].get(required_cmd, False)
                    effective_target = target if system_on and node_on else 0.0
                    cur = self.current[inst][param]
                    delta = effective_target - cur
                    cur += delta * 0.25
                    if effective_target > 0:
                        cur += random.uniform(-0.15, 0.15)
                    if cur < 0:
                        cur = 0.0
                    self.current[inst][param] = cur

    def snapshot_current(self):
        with self.lock:
            return {inst: values.copy() for inst, values in self.current.items()}

    def snapshot_status(self):
        with self.lock:
            return {
                "targets": {inst: values.copy() for inst, values in self.targets.items()},
                "current": {inst: values.copy() for inst, values in self.current.items()},
                "commands": {inst: values.copy() for inst, values in self.commands.items()},
                "faults": {inst: set(values) for inst, values in self.active_faults.items()},
                "telemetry_enabled": self.telemetry_enabled,
            }


def decode_and_apply_packet(raw: bytes, state: EmulatorState) -> str:
    hex_str = packet_to_hex(raw)
    if len(raw) != PACKET_LEN:
        return f"  [!] Неверная длина {len(raw)} байт | {hex_str}"
    if raw[0] != START_BYTE:
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
            f"{PARAM_NAMES[code]:24s} | цель = {value:8.2f}"
        )

    if code in CMD_NAMES:
        enabled = value >= 1.0
        state.set_command(inst, code, enabled)
        return (
            f"  [OK] КОМАНДА  | {inst_name:10s} | "
            f"{CMD_NAMES[code]:24s} | {'ВКЛ' if enabled else 'ВЫКЛ'}"
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
            idx = buf.find(START_BYTE)
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
    print(f"  Передача текущих параметров: период {SEND_PERIOD_SEC:.1f} сек\n")

    while not stop.is_set():
        if not state.is_telemetry_enabled():
            time.sleep(SEND_PERIOD_SEC)
            continue
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


def parse_install(text: str) -> int | None:
    return INSTALL_ALIASES.get(text.strip().lower())


def send_fault(port: serial.Serial, state: EmulatorState, inst: int, fault_name: str, active: bool = True):
    if fault_name not in ERROR_CODES or fault_name == "clear":
        print(f"  [!] Неизвестная авария: {fault_name}")
        print("      Доступно: propane, oxygen, air, feeder, pistol, general")
        return
    code = ERROR_CODES[fault_name]
    pkt = make_packet(inst, code, 1.0 if active else 0.0)
    try:
        port.write(pkt)
    except serial.SerialException as e:
        print(f"  [!] Не удалось отправить аварию: {e}")
        return
    state.set_fault(inst, fault_name, active)
    print(
        f"  [TX] АВАРИЯ | {INSTALL_NAMES[inst]:10s} | "
        f"{ERROR_NAMES[code]} | {'ON' if active else 'OFF'} | {packet_to_hex(pkt)}"
    )


def send_fault_clear(port: serial.Serial, state: EmulatorState, inst: int | None = None):
    installs = INSTALLS if inst is None else (inst,)
    for current_inst in installs:
        pkt = make_packet(current_inst, ERROR_CODES["clear"], 1.0)
        try:
            port.write(pkt)
        except serial.SerialException as e:
            print(f"  [!] Не удалось отправить сброс аварии: {e}")
            return
        print(f"  [TX] СБРОС АВАРИИ | {INSTALL_NAMES[current_inst]:10s} | {packet_to_hex(pkt)}")
    state.clear_faults(inst)


def print_status(state: EmulatorState):
    snapshot = state.snapshot_status()
    print("\n" + "-" * 72)
    print(f"  Телеметрия: {'ON' if snapshot['telemetry_enabled'] else 'OFF'}")
    for inst in INSTALLS:
        print(f"\n  {INSTALL_NAMES[inst]}")
        commands = snapshot["commands"][inst]
        faults = snapshot["faults"][inst]
        print("  Команды:")
        for code, title in CMD_NAMES.items():
            print(f"    {title:24s}: {'ON' if commands.get(code, False) else 'OFF'}")
        print("  Значения:")
        for param, title in PARAM_NAMES.items():
            target = snapshot["targets"][inst][param]
            current = snapshot["current"][inst][param]
            print(f"    {title:24s}: current={current:8.2f} target={target:8.2f}")
        print("  Аварии:")
        if faults:
            for fault in sorted(faults):
                print(f"    {fault}")
        else:
            print("    нет")
    print("-" * 72 + "\n")


def print_help():
    print(
        """
Команды эмулятора:
  help                         показать справку
  status                       показать состояние эмулятора

  fault wire propane           отправить аварию пропана для ПРОВОЛОКИ
  fault powder oxygen          отправить аварию кислорода для ПОРОШКА
  fault wire air               отправить аварию воздуха
  fault wire feeder            отправить аварию подачи
  fault wire pistol            отправить аварию пистолета/патателя
  fault wire general           отправить общую аварию

  clear wire                   сбросить аварию для ПРОВОЛОКИ
  clear powder                 сбросить аварию для ПОРОШКА
  clear all                    сбросить аварии для обеих установок

  telemetry on                 включить телеметрию
  telemetry off                выключить телеметрию для проверки потери связи

  quit                         выход
"""
    )


def console_loop(port: serial.Serial, state: EmulatorState, stop: threading.Event):
    print_help()
    while not stop.is_set():
        try:
            line = input("emu> ").strip()
        except (EOFError, KeyboardInterrupt):
            stop.set()
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("q", "quit", "exit"):
            stop.set()
            break
        if cmd in ("h", "help", "?"):
            print_help()
            continue
        if cmd == "status":
            print_status(state)
            continue
        if cmd == "telemetry":
            if len(parts) != 2 or parts[1].lower() not in ("on", "off"):
                print("  [!] Использование: telemetry on | telemetry off")
                continue
            enabled = parts[1].lower() == "on"
            state.set_telemetry(enabled)
            print(f"  [OK] Телеметрия {'включена' if enabled else 'выключена'}")
            continue
        if cmd == "fault":
            if len(parts) != 3:
                print("  [!] Использование: fault wire propane")
                continue
            inst = parse_install(parts[1])
            fault_name = parts[2].lower()
            if inst is None:
                print("  [!] Установка должна быть wire или powder")
                continue
            send_fault(port, state, inst, fault_name, True)
            continue
        if cmd == "clear":
            if len(parts) != 2:
                print("  [!] Использование: clear wire | clear powder | clear all")
                continue
            target = parts[1].lower()
            if target == "all":
                send_fault_clear(port, state, None)
                continue
            inst = parse_install(target)
            if inst is None:
                print("  [!] Установка должна быть wire, powder или all")
                continue
            send_fault_clear(port, state, inst)
            continue
        print("  [!] Неизвестная команда. Напишите help.")


def main():
    print("=" * 72)
    print("  HVoF UART Эмулятор с телеметрией и симуляцией аварий")
    print(f"  Порт: {PORT_NAME} | Baud: {BAUD_RATE}")
    print("  Ctrl+C или quit — выход")
    print("=" * 72)

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
    threads = [
        threading.Thread(target=receiver_loop, args=(port, state, stop), daemon=True),
        threading.Thread(target=telemetry_loop, args=(port, state, stop), daemon=True),
        threading.Thread(target=console_loop, args=(port, state, stop), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        while not stop.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n  Завершение...")
    finally:
        stop.set()
        time.sleep(0.2)
        port.close()
        print("  Порт закрыт")


if __name__ == "__main__":
    main()
