"""
emulator.py

Чистый Modbus RTU Slave-эмулятор для HMI HVoF.

ВАЖНО:
- Этот эмулятор НЕ использует pymodbus.
- Нужен только pyserial.
- Поэтому он не зависит от изменений API pymodbus 3.13 / 4.0.

Схема для Windows + com0com:
    HMI main.py  -> COM10
    emulator.py  -> COM11

Установка:
    python -m pip install pyserial

Запуск:
    python emulator.py

Поддерживаемые Modbus-функции:
    0x03 Read Holding Registers
    0x04 Read Input Registers
    0x06 Write Single Register
    0x10 Write Multiple Registers

Карта регистров:
    0..4      wire setpoints
    10..14    powder setpoints
    20        wire command mask
    21        powder command mask
    100..104  wire current values
    110..114  powder current values
    120       wire error mask
    121       powder error mask

Формат значений:
    float x10 -> uint16
    35.5 -> 355
"""

from __future__ import annotations

import random
import struct
import threading
import time
from dataclasses import dataclass, field

try:
    import serial
except ImportError as exc:
    print("pyserial не установлен.")
    print("Установите:")
    print("    python -m pip install pyserial")
    raise exc


# ─────────────────────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────────────────────

PORT_NAME = "COM11"
BAUD_RATE = 115200
SLAVE_ID = 1

SERIAL_TIMEOUT_SEC = 0.05
UPDATE_PERIOD_SEC = 0.25

SCALE = 10.0
REGISTER_COUNT = 300

# Логи.
# False — не печатать постоянные READ-запросы от HMI, чтобы не забивать консоль.
# True  — удобно для низкоуровневой отладки Modbus.
LOG_READ_REQUESTS = False

# Записи, аварии и важные события лучше оставить видимыми.
LOG_WRITE_REQUESTS = True

WIRE_SETPOINT_BASE = 0
POWDER_SETPOINT_BASE = 10

WIRE_COMMAND_REGISTER = 20
POWDER_COMMAND_REGISTER = 21

WIRE_CURRENT_BASE = 100
POWDER_CURRENT_BASE = 110

WIRE_ERROR_REGISTER = 120
POWDER_ERROR_REGISTER = 121

PARAM_NAMES = ("propane", "oxygen", "air", "feeder", "pistol")
PARAM_COUNT = len(PARAM_NAMES)

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

PARAM_TO_NODE_BIT = {
    "propane": COMMAND_BITS["propane_valve"],
    "oxygen": COMMAND_BITS["oxygen_valve"],
    "air": COMMAND_BITS["air_valve"],
    "feeder": COMMAND_BITS["feeder_motor"],
    "pistol": COMMAND_BITS["pistol_motor"],
}

ERROR_BITS = {
    "propane": 0,
    "oxygen": 1,
    "air": 2,
    "feeder": 3,
    "pistol": 4,
    "general": 5,
}


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def append_crc(data: bytes) -> bytes:
    crc = crc16_modbus(data)
    # Modbus RTU CRC передаётся little-endian: low byte, high byte.
    return data + struct.pack("<H", crc)


def check_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False

    received = struct.unpack("<H", frame[-2:])[0]
    calculated = crc16_modbus(frame[:-2])

    return received == calculated


def to_reg(value: float) -> int:
    raw = int(round(float(value) * SCALE))
    return max(0, min(0xFFFF, raw))


def from_reg(value: int) -> float:
    return int(value) / SCALE


def words_to_bytes(values: list[int]) -> bytes:
    return b"".join(struct.pack(">H", int(value) & 0xFFFF) for value in values)


@dataclass
class InstallRuntime:
    name: str
    setpoint_base: int
    command_register: int
    current_base: int
    error_register: int
    currents: dict[str, float] = field(
        default_factory=lambda: {name: 0.0 for name in PARAM_NAMES}
    )


class PureModbusSlaveEmulator:
    def __init__(self):
        self.running = True
        self.lock = threading.RLock()

        self.holding_registers = [0] * REGISTER_COUNT
        self.input_registers = [0] * REGISTER_COUNT

        self.installs = {
            "wire": InstallRuntime(
                name="wire",
                setpoint_base=WIRE_SETPOINT_BASE,
                command_register=WIRE_COMMAND_REGISTER,
                current_base=WIRE_CURRENT_BASE,
                error_register=WIRE_ERROR_REGISTER,
            ),
            "powder": InstallRuntime(
                name="powder",
                setpoint_base=POWDER_SETPOINT_BASE,
                command_register=POWDER_COMMAND_REGISTER,
                current_base=POWDER_CURRENT_BASE,
                error_register=POWDER_ERROR_REGISTER,
            ),
        }

    # ─────────────────────────────────────────────────────────────
    # Регистры
    # ─────────────────────────────────────────────────────────────

    def read_holding(self, address: int, count: int) -> list[int]:
        with self.lock:
            self._validate_range(address, count)
            return list(self.holding_registers[address:address + count])

    def read_input(self, address: int, count: int) -> list[int]:
        with self.lock:
            self._validate_range(address, count)
            return list(self.input_registers[address:address + count])

    def write_holding(self, address: int, values: list[int]):
        with self.lock:
            self._validate_range(address, len(values))

            for index, value in enumerate(values):
                raw = int(value) & 0xFFFF
                self.holding_registers[address + index] = raw

                # Дублируем в input registers, чтобы HMI мог читать значения
                # функцией 03 или 04.
                self.input_registers[address + index] = raw

    def _validate_range(self, address: int, count: int):
        if address < 0 or count < 1 or address + count > REGISTER_COUNT:
            raise ValueError(f"Недопустимый диапазон регистров: address={address}, count={count}")

    # ─────────────────────────────────────────────────────────────
    # Модель установки
    # ─────────────────────────────────────────────────────────────

    def update_loop(self):
        while self.running:
            try:
                for install in self.installs.values():
                    self.update_install(install)
            except Exception as exc:
                print("[EMU] update error:", exc)

            time.sleep(UPDATE_PERIOD_SEC)

    def update_install(self, install: InstallRuntime):
        setpoint_regs = self.read_holding(install.setpoint_base, PARAM_COUNT)
        command_mask = self.read_holding(install.command_register, 1)[0]
        error_mask = self.read_holding(install.error_register, 1)[0]

        system_on = bool(command_mask & (1 << COMMAND_BITS["main_system"]))
        general_fault = bool(error_mask & (1 << ERROR_BITS["general"]))

        current_regs = []

        for index, param_name in enumerate(PARAM_NAMES):
            target = from_reg(setpoint_regs[index])

            node_bit = PARAM_TO_NODE_BIT[param_name]
            node_on = bool(command_mask & (1 << node_bit))

            param_fault = bool(error_mask & (1 << ERROR_BITS[param_name]))

            if system_on and node_on and not general_fault and not param_fault:
                effective_target = target
            else:
                effective_target = 0.0

            current = install.currents[param_name]
            current += (effective_target - current) * 0.20

            if effective_target > 0.0:
                current += random.uniform(-0.12, 0.12)

            if current < 0.03:
                current = 0.0

            install.currents[param_name] = current
            current_regs.append(to_reg(current))

        self.write_holding(install.current_base, current_regs)

    # ─────────────────────────────────────────────────────────────
    # Modbus RTU serial loop
    # ─────────────────────────────────────────────────────────────

    def serial_loop(self):
        try:
            port = serial.Serial(
                port=PORT_NAME,
                baudrate=BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=SERIAL_TIMEOUT_SEC,
            )
        except Exception as exc:
            print(f"[EMU] Не удалось открыть {PORT_NAME}: {exc}")
            self.running = False
            return

        print(f"[EMU] Serial открыт: {PORT_NAME} @ {BAUD_RATE}")

        rx = bytearray()

        try:
            while self.running:
                chunk = port.read(port.in_waiting or 1)

                if chunk:
                    rx.extend(chunk)

                    while True:
                        frame = self._try_extract_frame(rx)
                        if frame is None:
                            break

                        response = self.handle_frame(frame)

                        if response:
                            port.write(response)

                elif len(rx) > 260:
                    rx.clear()

        except KeyboardInterrupt:
            pass
        except Exception as exc:
            print("[EMU] serial error:", exc)
        finally:
            try:
                port.close()
            except Exception:
                pass

            self.running = False
            print("[EMU] Serial закрыт")

    def _try_extract_frame(self, rx: bytearray) -> bytes | None:
        """
        Извлекает один Modbus RTU request из буфера.
        Поддерживаем функции 03, 04, 06, 10.
        """
        while rx and rx[0] != SLAVE_ID:
            del rx[0]

        if len(rx) < 2:
            return None

        func = rx[1]

        # 03/04/06 запросы фиксированной длины 8 байт.
        if func in (0x03, 0x04, 0x06):
            expected_len = 8

            if len(rx) < expected_len:
                return None

            frame = bytes(rx[:expected_len])
            del rx[:expected_len]
            return frame

        # 10 Write Multiple Registers:
        # slave + func + address(2) + count(2) + byte_count(1) + data + crc(2)
        if func == 0x10:
            if len(rx) < 7:
                return None

            byte_count = rx[6]
            expected_len = 7 + byte_count + 2

            if len(rx) < expected_len:
                return None

            frame = bytes(rx[:expected_len])
            del rx[:expected_len]
            return frame

        # Неизвестная функция. Удаляем первый байт, чтобы не зависнуть.
        del rx[0]
        return None

    def handle_frame(self, frame: bytes) -> bytes | None:
        if not check_crc(frame):
            print("[EMU RX] CRC error:", frame.hex(" ").upper())
            return None

        slave = frame[0]
        func = frame[1]

        if slave != SLAVE_ID:
            return None

        try:
            if func == 0x03:
                return self.handle_read_registers(frame, input_registers=False)

            if func == 0x04:
                return self.handle_read_registers(frame, input_registers=True)

            if func == 0x06:
                return self.handle_write_single(frame)

            if func == 0x10:
                return self.handle_write_multiple(frame)

            return self.exception_response(func, 0x01)

        except Exception as exc:
            print("[EMU] handle error:", exc)
            return self.exception_response(func, 0x04)

    def handle_read_registers(self, frame: bytes, input_registers: bool) -> bytes:
        _, func, address, count = struct.unpack(">BBHH", frame[:6])

        if count < 1 or count > 125:
            return self.exception_response(func, 0x03)

        try:
            values = self.read_input(address, count) if input_registers else self.read_holding(address, count)
        except ValueError:
            return self.exception_response(func, 0x02)

        payload = bytes([SLAVE_ID, func, count * 2]) + words_to_bytes(values)
        response = append_crc(payload)

        if LOG_READ_REQUESTS:
            print(f"[EMU RX] READ {'IR' if input_registers else 'HR'} addr={address} count={count}")

        return response

    def handle_write_single(self, frame: bytes) -> bytes:
        _, func, address, value = struct.unpack(">BBHH", frame[:6])

        try:
            self.write_holding(address, [value])
        except ValueError:
            return self.exception_response(func, 0x02)

        if LOG_WRITE_REQUESTS:
            print(f"[EMU RX] WRITE HR addr={address} value={value}")

        # Для функции 06 ответ = эхо запроса.
        return append_crc(frame[:-2])

    def handle_write_multiple(self, frame: bytes) -> bytes:
        slave = frame[0]
        func = frame[1]
        address = struct.unpack(">H", frame[2:4])[0]
        count = struct.unpack(">H", frame[4:6])[0]
        byte_count = frame[6]

        if count < 1 or count > 123 or byte_count != count * 2:
            return self.exception_response(func, 0x03)

        values = []

        offset = 7
        for _ in range(count):
            values.append(struct.unpack(">H", frame[offset:offset + 2])[0])
            offset += 2

        try:
            self.write_holding(address, values)
        except ValueError:
            return self.exception_response(func, 0x02)

        if LOG_WRITE_REQUESTS:
            print(f"[EMU RX] WRITE MULTI HR addr={address} count={count} values={values}")

        payload = struct.pack(">BBHH", slave, func, address, count)
        return append_crc(payload)

    def exception_response(self, func: int, code: int) -> bytes:
        payload = bytes([SLAVE_ID, func | 0x80, code])
        return append_crc(payload)

    # ─────────────────────────────────────────────────────────────
    # Консоль
    # ─────────────────────────────────────────────────────────────

    def console_loop(self):
        print_help()

        while self.running:
            try:
                line = input("modbus-emu> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.running = False
                break

            if not line:
                continue

            parts = line.split()
            command = parts[0].lower()

            try:
                if command in ("q", "quit", "exit"):
                    self.running = False
                    break

                if command in ("h", "help", "?"):
                    print_help()
                    continue

                if command == "status":
                    self.print_status()
                    continue

                if command == "log":
                    self.cmd_log(parts)
                    continue

                if command == "fault":
                    self.cmd_fault(parts)
                    continue

                if command == "clear":
                    self.cmd_clear(parts)
                    continue

                if command == "set":
                    self.cmd_set(parts)
                    continue

                if command == "cmd":
                    self.cmd_command_mask(parts)
                    continue

                print("Неизвестная команда. Напишите help.")

            except Exception as exc:
                print("[EMU] command error:", exc)

    def cmd_log(self, parts: list[str]):
        """
        Управление логами:
            log read on
            log read off
            log write on
            log write off
        """
        global LOG_READ_REQUESTS, LOG_WRITE_REQUESTS

        if len(parts) != 3:
            print("Использование: log read on | log read off | log write on | log write off")
            return

        target = parts[1].lower()
        state = parts[2].lower()

        if state not in ("on", "off"):
            print("Состояние должно быть on или off.")
            return

        enabled = state == "on"

        if target == "read":
            LOG_READ_REQUESTS = enabled
            print(f"[EMU] READ logs: {'ON' if enabled else 'OFF'}")
            return

        if target == "write":
            LOG_WRITE_REQUESTS = enabled
            print(f"[EMU] WRITE logs: {'ON' if enabled else 'OFF'}")
            return

        print("Тип логов должен быть read или write.")

    def cmd_fault(self, parts: list[str]):
        if len(parts) != 3:
            print("Использование: fault wire propane")
            return

        install_name = parts[1].lower()
        fault_name = parts[2].lower()

        install = self.installs.get(install_name)
        if install is None:
            print("Установка должна быть wire или powder.")
            return

        bit = ERROR_BITS.get(fault_name)
        if bit is None:
            print("Авария должна быть: propane, oxygen, air, feeder, pistol, general.")
            return

        mask = self.read_holding(install.error_register, 1)[0]
        mask |= 1 << bit
        self.write_holding(install.error_register, [mask])

        print(f"[EMU] fault {install_name} {fault_name}: error_mask=0x{mask:04X}")

    def cmd_clear(self, parts: list[str]):
        if len(parts) != 2:
            print("Использование: clear wire | clear powder | clear all")
            return

        target = parts[1].lower()

        if target == "all":
            for install in self.installs.values():
                self.write_holding(install.error_register, [0])
            print("[EMU] Все аварии сброшены.")
            return

        install = self.installs.get(target)
        if install is None:
            print("Установка должна быть wire, powder или all.")
            return

        self.write_holding(install.error_register, [0])
        print(f"[EMU] Аварии сброшены: {target}")

    def cmd_set(self, parts: list[str]):
        if len(parts) != 4:
            print("Использование: set wire propane 35.5")
            return

        install_name = parts[1].lower()
        param_name = parts[2].lower()
        value = float(parts[3].replace(",", "."))

        install = self.installs.get(install_name)
        if install is None:
            print("Установка должна быть wire или powder.")
            return

        if param_name not in PARAM_NAMES:
            print("Параметр должен быть: propane, oxygen, air, feeder, pistol.")
            return

        index = PARAM_NAMES.index(param_name)
        address = install.setpoint_base + index
        raw = to_reg(value)

        self.write_holding(address, [raw])

        print(f"[EMU] set {install_name} {param_name}={value:.2f} -> reg={address} raw={raw}")

    def cmd_command_mask(self, parts: list[str]):
        """
        Ручная установка командной маски:
            cmd wire 0039
            cmd powder 0
        """
        if len(parts) != 3:
            print("Использование: cmd wire 0039 | cmd powder 0")
            return

        install_name = parts[1].lower()
        raw_mask = parts[2].lower().replace("0x", "")

        install = self.installs.get(install_name)
        if install is None:
            print("Установка должна быть wire или powder.")
            return

        try:
            mask = int(raw_mask, 16)
        except ValueError:
            mask = int(raw_mask)

        self.write_holding(install.command_register, [mask])
        print(f"[EMU] command mask {install_name}: 0x{mask:04X}")

    def print_status(self):
        print()
        print("=" * 72)
        print("STATUS")
        print("=" * 72)

        for install_name, install in self.installs.items():
            setpoints = self.read_holding(install.setpoint_base, PARAM_COUNT)
            currents = self.read_holding(install.current_base, PARAM_COUNT)
            command_mask = self.read_holding(install.command_register, 1)[0]
            error_mask = self.read_holding(install.error_register, 1)[0]

            print()
            print(install_name.upper())
            print(f"  setpoint regs: {install.setpoint_base}..{install.setpoint_base + PARAM_COUNT - 1}")
            print(f"  current regs:  {install.current_base}..{install.current_base + PARAM_COUNT - 1}")
            print(f"  command reg:   {install.command_register}, mask=0x{command_mask:04X}")
            print(f"  error reg:     {install.error_register}, mask=0x{error_mask:04X}")
            print()

            for name, sp_reg, cur_reg in zip(PARAM_NAMES, setpoints, currents):
                print(
                    f"  {name:8s} | setpoint={from_reg(sp_reg):8.2f} "
                    f"| current={from_reg(cur_reg):8.2f}"
                )

        print()


def print_help():
    print(
        """
Команды эмулятора:

  help
  status

  log read on
  log read off
  log write on
  log write off

  fault wire propane
  fault wire oxygen
  fault wire air
  fault wire feeder
  fault wire pistol
  fault wire general

  fault powder propane
  fault powder oxygen
  fault powder air
  fault powder feeder
  fault powder pistol
  fault powder general

  clear wire
  clear powder
  clear all

  set wire propane 35.5
  set powder oxygen 120

  cmd wire 0039
  cmd powder 0

  quit
"""
    )


def main():
    print("=" * 72)
    print("HVoF Pure Modbus RTU Slave Emulator")
    print(f"PORT={PORT_NAME} | BAUD={BAUD_RATE} | SLAVE_ID={SLAVE_ID}")
    print("Backend: pyserial only, no pymodbus")
    print(f"READ logs: {'ON' if LOG_READ_REQUESTS else 'OFF'} | WRITE logs: {'ON' if LOG_WRITE_REQUESTS else 'OFF'}")
    print("=" * 72)

    emulator = PureModbusSlaveEmulator()

    threading.Thread(target=emulator.update_loop, daemon=True).start()
    threading.Thread(target=emulator.console_loop, daemon=True).start()

    emulator.serial_loop()


if __name__ == "__main__":
    main()
