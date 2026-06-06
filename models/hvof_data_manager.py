"""
models/hvof_data_manager.py

Modbus RTU DataManager для HMI HVoF.

Этот файл заменяет старый UART-пакетный обмен.
Физический уровень остаётся UART/COM, протокол обмена — Modbus RTU.

Интерфейс для остального приложения сохранён:

MainViewModel -> DataManager:
    send_setpoint_packet(install, param, value)
    send_command_packet(install, command, state)

DataManager -> MainViewModel:
    currentValueChanged(install, param, value)
    errorStateChanged(install, has_error, message)
    linkStateChanged(install, connected)

Дополнительно добавлены сигналы синхронизации:
    setpointValueChanged(install, param, value)
    commandMaskChanged(install, mask)
    commandStateChanged(install, command, state)
    writeFailed(install, operation, message)

Если эти дополнительные сигналы пока никуда не подключены, приложение всё равно
будет работать как раньше.
"""

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

try:
    from pymodbus.client import ModbusSerialClient
    _PYMODBUS_AVAILABLE = True
except Exception:
    ModbusSerialClient = None
    _PYMODBUS_AVAILABLE = False

from utils.constants import (
    INSTALL_TYPES,
    SERIAL_PORT,
    SERIAL_BAUD,
    SERIAL_TIMEOUT_SEC,
    UART_LINK_TIMEOUT_MS,
)

from utils.modbus_map import (
    MODBUS_SLAVE_ID,
    MODBUS_POLL_INTERVAL_MS,
    MODBUS_LINK_TIMEOUT_MS,
    MODBUS_SLOW_POLL_EVERY,
    PARAM_ORDER,
    SETPOINT_BASE,
    COMMAND_REGISTER,
    CURRENT_BASE,
    ERROR_REGISTER,
    COMMAND_BITS,
    scale_to_register,
    would_clip_register,
    register_to_float,
    setpoint_address,
    command_mask_set,
    command_mask_to_states,
    error_mask_to_message,
)


# ─────────────────────────────────────────────────────────────
# Настройка чтения регистров от МК
# ─────────────────────────────────────────────────────────────
# False:
#   читать текущие значения / ошибки функцией 0x03 Read Holding Registers.
#
# True:
#   читать текущие значения / ошибки функцией 0x04 Read Input Registers.
#
# Если разработчики МК сделают текущие значения и аварии как Input Registers,
# поменять соответствующий флаг на True.

MODBUS_READ_CURRENT_AS_INPUT_REGISTERS = False
MODBUS_READ_ERRORS_AS_INPUT_REGISTERS = False


class HvofDataManager(QObject):
    logMessage = pyqtSignal(str)

    # install, param, value
    currentValueChanged = pyqtSignal(str, str, float)

    # install, param, value
    setpointValueChanged = pyqtSignal(str, str, float)

    # install, has_error, message
    errorStateChanged = pyqtSignal(str, bool, str)

    # install, connected
    linkStateChanged = pyqtSignal(str, bool)

    # install, mask
    commandMaskChanged = pyqtSignal(str, int)

    # install, command, state
    commandStateChanged = pyqtSignal(str, str, bool)

    # install, operation, message
    writeFailed = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._client = None
        self._poll_timer = None
        self._watchdog_timer = None
        self._poll_counter = 0

        self._last_rx_ms = {install: 0 for install in INSTALL_TYPES}
        self._link_ok = {install: False for install in INSTALL_TYPES}

        # Локальное состояние командной маски.
        # Обновляется:
        # - после успешной записи команды;
        # - после успешного чтения COMMAND_REGISTER из МК.
        self._command_masks = {install: 0 for install in INSTALL_TYPES}

        # Последняя принятая маска ошибок, чтобы не спамить одинаковыми сообщениями.
        self._last_error_masks = {install: None for install in INSTALL_TYPES}

    # ─────────────────────────────────────────────────────────────
    # Открытие / закрытие Modbus RTU
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def open_port(self):
        # Защита от повторного открытия без закрытия.
        if self._client is not None or self._poll_timer is not None or self._watchdog_timer is not None:
            self.close_port()

        if not _PYMODBUS_AVAILABLE:
            self.logMessage.emit(
                "[MODBUS] pymodbus не установлен. "
                "Установите: python -m pip install pymodbus pyserial"
            )
            return

        if not SERIAL_PORT:
            self.logMessage.emit("[MODBUS] SERIAL_PORT не задан")
            return

        try:
            self._client = self._create_client()
            connected = self._client.connect()

            if not connected:
                self.logMessage.emit(
                    f"[MODBUS] Не удалось открыть порт {SERIAL_PORT} @ {SERIAL_BAUD}"
                )
                self._client = None

                for install in INSTALL_TYPES:
                    self._set_link_state(install, False)

                return

            self.logMessage.emit(
                f"[MODBUS] RTU master открыт: "
                f"{SERIAL_PORT} @ {SERIAL_BAUD}, slave_id={MODBUS_SLAVE_ID}"
            )

            self._poll_counter = 0

            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(MODBUS_POLL_INTERVAL_MS)
            self._poll_timer.timeout.connect(self._poll_device)
            self._poll_timer.start()

            self._watchdog_timer = QtCore.QTimer(self)
            self._watchdog_timer.setInterval(500)
            self._watchdog_timer.timeout.connect(self._check_link_watchdog)
            self._watchdog_timer.start()

            # Первый опрос сразу после подключения, чтобы синхронизировать состояние.
            QtCore.QTimer.singleShot(0, self._poll_device)

        except Exception as e:
            self._client = None
            self.logMessage.emit(f"[MODBUS] Ошибка открытия порта {SERIAL_PORT}: {e}")

            for install in INSTALL_TYPES:
                self._set_link_state(install, False)

    def _create_client(self):
        """
        Создание ModbusSerialClient с учётом разных версий pymodbus.

        pymodbus 2.x:
            ModbusSerialClient(method="rtu", port=...)

        pymodbus 3.x:
            ModbusSerialClient(port=...)
        """
        common_kwargs = dict(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUD,
            timeout=max(0.2, float(SERIAL_TIMEOUT_SEC or 0.2)),
            bytesize=8,
            parity="N",
            stopbits=1,
        )

        try:
            return ModbusSerialClient(method="rtu", **common_kwargs)
        except TypeError:
            return ModbusSerialClient(**common_kwargs)

    @pyqtSlot()
    def close_port(self):
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

        if self._watchdog_timer is not None:
            self._watchdog_timer.stop()
            self._watchdog_timer.deleteLater()
            self._watchdog_timer = None

        if self._client is not None:
            try:
                self._client.close()
                self.logMessage.emit("[MODBUS] Порт закрыт")
            except Exception as e:
                self.logMessage.emit(f"[MODBUS] Ошибка закрытия порта: {e}")

        self._client = None
        self._poll_counter = 0

        for install in INSTALL_TYPES:
            self._set_link_state(install, False)

    # ─────────────────────────────────────────────────────────────
    # Передача HMI -> МК
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, float)
    def send_setpoint_packet(self, install_type: str, param_name: str, value: float):
        """
        Сохранено старое имя метода, чтобы не менять main.py и MainViewModel.

        Modbus:
            write_register(setpoint_address, scaled_value)
        """
        if install_type not in SETPOINT_BASE:
            self.logMessage.emit(f"[MODBUS TX] Неизвестная установка: {install_type}")
            return

        if not self._link_ok.get(install_type, False):
            self.logMessage.emit(
                f"[MODBUS TX] Связь с {install_type.upper()} не подтверждена, пробуем отправить уставку"
            )

        try:
            address = setpoint_address(install_type, param_name)
        except KeyError:
            self.logMessage.emit(f"[MODBUS TX] Неизвестный параметр: {param_name}")
            return

        if would_clip_register(value):
            self.logMessage.emit(
                f"[MODBUS TX] Предупреждение: значение {param_name}={value} "
                f"будет ограничено диапазоном uint16 при масштабе x10"
            )

        raw_value = scale_to_register(value)
        ok = self._write_register(address, raw_value, install_type=install_type)

        if not ok:
            self.writeFailed.emit(
                install_type,
                f"setpoint:{param_name}",
                f"Не удалось записать уставку {param_name}",
            )

        self.logMessage.emit(
            f"[MODBUS TX] SETPOINT {install_type.upper()} "
            f"{param_name}={value:.2f} -> reg={address} raw={raw_value} "
            f"{'OK' if ok else 'FAIL'}"
        )

    @pyqtSlot(str, str, bool)
    def send_command_packet(self, install_type: str, command_name: str, state: bool):
        """
        Сохранено старое имя метода, чтобы не менять main.py и MainViewModel.

        Modbus:
            write_register(command_register, command_bit_mask)
        """
        if install_type not in COMMAND_REGISTER:
            self.logMessage.emit(f"[MODBUS TX] Неизвестная установка: {install_type}")
            return

        if command_name not in COMMAND_BITS:
            self.logMessage.emit(f"[MODBUS TX] Неизвестная команда: {command_name}")
            return

        if not self._link_ok.get(install_type, False):
            self.logMessage.emit(
                f"[MODBUS TX] Связь с {install_type.upper()} не подтверждена, пробуем отправить команду"
            )

        old_mask = self._command_masks[install_type]
        new_mask = command_mask_set(old_mask, command_name, bool(state))

        address = COMMAND_REGISTER[install_type]
        ok = self._write_register(address, new_mask, install_type=install_type)

        # Важно:
        # локальную маску обновляем только если запись в МК прошла успешно.
        # Иначе HMI может думать, что команда включена, хотя МК её не получил.
        if ok:
            self._update_command_mask(install_type, new_mask)

        else:
            self.writeFailed.emit(
                install_type,
                f"command:{command_name}",
                f"Не удалось записать команду {command_name}",
            )

        self.logMessage.emit(
            f"[MODBUS TX] COMMAND {install_type.upper()} "
            f"{command_name}={'ON' if state else 'OFF'} "
            f"-> reg={address} mask=0x{new_mask:04X} "
            f"{'OK' if ok else 'FAIL'}"
        )

    def _write_register(self, address: int, value: int, install_type: str | None = None) -> bool:
        if self._client is None:
            self.logMessage.emit("[MODBUS TX] Нет подключения")
            return False

        try:
            result = self._call_modbus(
                self._client.write_register,
                address=int(address),
                value=int(value) & 0xFFFF,
            )

            ok = not self._is_error(result)

            # Успешная запись означает, что slave ответил.
            # Это тоже подтверждение связи.
            if ok and install_type in self._last_rx_ms:
                self._mark_rx(install_type)

            return ok

        except Exception as e:
            self.logMessage.emit(f"[MODBUS TX] Ошибка записи reg={address}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Приём МК -> HMI
    # ─────────────────────────────────────────────────────────────

    def _poll_device(self):
        if self._client is None:
            return

        self._poll_counter += 1
        slow_poll = self._poll_counter % max(1, int(MODBUS_SLOW_POLL_EVERY)) == 0

        for install in INSTALL_TYPES:
            self._poll_current_values(install)
            self._poll_error_state(install)

            if slow_poll:
                self._poll_setpoints(install)
                self._poll_commands(install)

    def _poll_current_values(self, install_type: str):
        base = CURRENT_BASE[install_type]

        try:
            if MODBUS_READ_CURRENT_AS_INPUT_REGISTERS:
                result = self._call_modbus(
                    self._client.read_input_registers,
                    address=int(base),
                    count=len(PARAM_ORDER),
                )
            else:
                result = self._call_modbus(
                    self._client.read_holding_registers,
                    address=int(base),
                    count=len(PARAM_ORDER),
                )

            if self._is_error(result):
                self.logMessage.emit(
                    f"[MODBUS RX] Ошибка чтения текущих "
                    f"{install_type.upper()} base={base}"
                )
                return

            registers = list(getattr(result, "registers", []) or [])

            if len(registers) < len(PARAM_ORDER):
                self.logMessage.emit(
                    f"[MODBUS RX] Мало регистров "
                    f"{install_type.upper()}: {len(registers)}"
                )
                return

            self._mark_rx(install_type)

            for index, param_name in enumerate(PARAM_ORDER):
                value = register_to_float(registers[index])
                self.currentValueChanged.emit(install_type, param_name, value)

        except Exception as e:
            self.logMessage.emit(
                f"[MODBUS RX] Ошибка чтения текущих {install_type.upper()}: {e}"
            )

    def _poll_setpoints(self, install_type: str):
        """
        Медленное чтение уставок из МК.

        Это нужно для синхронизации после перезапуска HMI/МК.
        Основной UI можно подключить к setpointValueChanged, если МК должен быть
        источником истины по уставкам.
        """
        base = SETPOINT_BASE[install_type]

        try:
            result = self._call_modbus(
                self._client.read_holding_registers,
                address=int(base),
                count=len(PARAM_ORDER),
            )

            if self._is_error(result):
                self.logMessage.emit(
                    f"[MODBUS RX] Ошибка чтения уставок "
                    f"{install_type.upper()} base={base}"
                )
                return

            registers = list(getattr(result, "registers", []) or [])

            if len(registers) < len(PARAM_ORDER):
                self.logMessage.emit(
                    f"[MODBUS RX] Мало регистров уставок "
                    f"{install_type.upper()}: {len(registers)}"
                )
                return

            self._mark_rx(install_type)

            for index, param_name in enumerate(PARAM_ORDER):
                value = register_to_float(registers[index])
                self.setpointValueChanged.emit(install_type, param_name, value)

            self.logMessage.emit(
                f"[MODBUS RX] SETPOINTS {install_type.upper()} "
                f"regs={base}..{base + len(PARAM_ORDER) - 1}"
            )

        except Exception as e:
            self.logMessage.emit(
                f"[MODBUS RX] Ошибка чтения уставок {install_type.upper()}: {e}"
            )

    def _poll_commands(self, install_type: str):
        """
        Медленное чтение командной маски из МК.

        Это синхронизирует _command_masks после старта HMI или после перезапуска МК.
        """
        address = COMMAND_REGISTER[install_type]

        try:
            result = self._call_modbus(
                self._client.read_holding_registers,
                address=int(address),
                count=1,
            )

            if self._is_error(result):
                self.logMessage.emit(
                    f"[MODBUS RX] Ошибка чтения команд "
                    f"{install_type.upper()} reg={address}"
                )
                return

            registers = list(getattr(result, "registers", []) or [])
            mask = int(registers[0]) if registers else 0

            self._mark_rx(install_type)
            self._update_command_mask(install_type, mask)

            self.logMessage.emit(
                f"[MODBUS RX] COMMANDS {install_type.upper()} "
                f"reg={address} mask=0x{mask:04X}"
            )

        except Exception as e:
            self.logMessage.emit(
                f"[MODBUS RX] Ошибка чтения команд {install_type.upper()}: {e}"
            )

    def _poll_error_state(self, install_type: str):
        address = ERROR_REGISTER[install_type]

        try:
            if MODBUS_READ_ERRORS_AS_INPUT_REGISTERS:
                result = self._call_modbus(
                    self._client.read_input_registers,
                    address=int(address),
                    count=1,
                )
            else:
                result = self._call_modbus(
                    self._client.read_holding_registers,
                    address=int(address),
                    count=1,
                )

            if self._is_error(result):
                self.logMessage.emit(
                    f"[MODBUS RX] Ошибка чтения аварий "
                    f"{install_type.upper()} reg={address}"
                )
                return

            registers = list(getattr(result, "registers", []) or [])
            mask = int(registers[0]) if registers else 0

            # Успешное чтение регистра аварий тоже подтверждает связь.
            self._mark_rx(install_type)

            if self._last_error_masks[install_type] == mask:
                return

            self._last_error_masks[install_type] = mask

            has_error, message = error_mask_to_message(mask)
            self.errorStateChanged.emit(install_type, has_error, message)

            self.logMessage.emit(
                f"[MODBUS RX] ERROR {install_type.upper()} "
                f"reg={address} mask=0x{mask:04X} "
                f"{message if has_error else 'нет аварий'}"
            )

        except Exception as e:
            self.logMessage.emit(
                f"[MODBUS RX] Ошибка чтения аварий {install_type.upper()}: {e}"
            )

    # ─────────────────────────────────────────────────────────────
    # Командная маска
    # ─────────────────────────────────────────────────────────────

    def _update_command_mask(self, install_type: str, mask: int):
        mask = int(mask) & 0xFFFF
        old_mask = int(self._command_masks.get(install_type, 0)) & 0xFFFF

        if old_mask == mask:
            return

        self._command_masks[install_type] = mask
        self.commandMaskChanged.emit(install_type, mask)

        old_states = command_mask_to_states(old_mask)
        new_states = command_mask_to_states(mask)

        for command_name, new_state in new_states.items():
            if old_states.get(command_name) != new_state:
                self.commandStateChanged.emit(install_type, command_name, new_state)

    # ─────────────────────────────────────────────────────────────
    # Совместимость с разными версиями pymodbus
    # ─────────────────────────────────────────────────────────────

    def _call_modbus(self, func, **kwargs):
        """
        Разные версии pymodbus используют разные имена аргумента Slave ID:
            device_id — актуально для pymodbus 3.13+
            slave     — часть версий pymodbus 3.x
            unit      — старые версии pymodbus

        Сначала пробуем device_id.
        """
        last_error = None

        for slave_kw in ("device_id", "slave", "unit"):
            try:
                return func(**kwargs, **{slave_kw: MODBUS_SLAVE_ID})
            except TypeError as e:
                last_error = e
                continue

        if last_error is not None:
            raise last_error

        raise TypeError("Не удалось вызвать Modbus-функцию: неизвестная сигнатура pymodbus")

    @staticmethod
    def _is_error(result) -> bool:
        if result is None:
            return True

        is_error = getattr(result, "isError", None)

        if callable(is_error):
            return bool(is_error())

        return False

    # ─────────────────────────────────────────────────────────────
    # Watchdog связи
    # ─────────────────────────────────────────────────────────────

    def _mark_rx(self, install_type: str):
        self._last_rx_ms[install_type] = QtCore.QDateTime.currentMSecsSinceEpoch()
        self._set_link_state(install_type, True)

    def _set_link_state(self, install_type: str, connected: bool):
        if install_type not in self._link_ok:
            return

        connected = bool(connected)

        if self._link_ok[install_type] == connected:
            return

        self._link_ok[install_type] = connected
        self.linkStateChanged.emit(install_type, connected)

        if connected:
            self.logMessage.emit(f"[MODBUS] Связь восстановлена: {install_type.upper()}")
        else:
            self.logMessage.emit(f"[MODBUS] Нет связи: {install_type.upper()}")

    def _check_link_watchdog(self):
        timeout_ms = MODBUS_LINK_TIMEOUT_MS or UART_LINK_TIMEOUT_MS
        now = QtCore.QDateTime.currentMSecsSinceEpoch()

        for install in INSTALL_TYPES:
            last_rx = self._last_rx_ms.get(install, 0)

            if last_rx <= 0:
                self._set_link_state(install, False)
                continue

            self._set_link_state(install, now - last_rx <= timeout_ms)
