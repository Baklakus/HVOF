"""
models/hvof_data_manager.py

Model / DataManager для обмена HMI HVoF с микроконтроллером.
"""

try:
    import serial as _serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from utils.constants import (
    INSTALL_TYPES,
    SERIAL_PORT,
    SERIAL_BAUD,
    SERIAL_TIMEOUT_SEC,
    UART_POLL_INTERVAL_MS,
    UART_LINK_TIMEOUT_MS,
)
from utils.uart_protocol import (
    PACKET_LEN,
    UartProtocolError,
    classify_packet_code,
    find_packet_in_buffer,
    make_setpoint_packet,
    make_command_packet,
    parse_current_value_packet,
    parse_error_packet,
    parse_float_packet,
    packet_to_hex,
)


class HvofDataManager(QObject):
    logMessage = pyqtSignal(str)

    # install, param, value
    currentValueChanged = pyqtSignal(str, str, float)

    # install, has_error, message
    errorStateChanged = pyqtSignal(str, bool, str)

    # install, connected
    linkStateChanged = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = None
        self._rx_buf = bytearray()
        self._rx_timer = None
        self._watchdog_timer = None
        self._last_rx_ms = {install: 0 for install in INSTALL_TYPES}
        self._link_ok = {install: False for install in INSTALL_TYPES}

    # ─────────────────────────────────────────────────────────────
    # Открытие / закрытие порта
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def open_port(self):
        if not _SERIAL_AVAILABLE:
            self.logMessage.emit("[UART] pyserial не установлен — режим лога")
            return

        if not SERIAL_PORT:
            self.logMessage.emit("[UART] SERIAL_PORT не задан — режим лога")
            return

        try:
            self._port = _serial.Serial(
                port=SERIAL_PORT,
                baudrate=SERIAL_BAUD,
                bytesize=_serial.EIGHTBITS,
                parity=_serial.PARITY_NONE,
                stopbits=_serial.STOPBITS_ONE,
                timeout=SERIAL_TIMEOUT_SEC,
            )

            self.logMessage.emit(f"[UART] Порт открыт: {SERIAL_PORT} @ {SERIAL_BAUD}")

            self._rx_timer = QtCore.QTimer(self)
            self._rx_timer.setInterval(UART_POLL_INTERVAL_MS)
            self._rx_timer.timeout.connect(self._poll_port)
            self._rx_timer.start()

            self._watchdog_timer = QtCore.QTimer(self)
            self._watchdog_timer.setInterval(500)
            self._watchdog_timer.timeout.connect(self._check_link_watchdog)
            self._watchdog_timer.start()

        except Exception as e:
            self._port = None
            self.logMessage.emit(f"[UART] Ошибка порта {SERIAL_PORT}: {e}")
            for install in INSTALL_TYPES:
                self._set_link_state(install, False)

    @pyqtSlot()
    def close_port(self):
        if self._rx_timer is not None:
            self._rx_timer.stop()
            self._rx_timer.deleteLater()
            self._rx_timer = None

        if self._watchdog_timer is not None:
            self._watchdog_timer.stop()
            self._watchdog_timer.deleteLater()
            self._watchdog_timer = None

        if self._port is not None:
            try:
                if self._port.is_open:
                    self._port.close()
                    self.logMessage.emit("[UART] Порт закрыт")
            except Exception as e:
                self.logMessage.emit(f"[UART] Ошибка закрытия порта: {e}")
            self._port = None

        self._rx_buf.clear()
        for install in INSTALL_TYPES:
            self._set_link_state(install, False)

    # ─────────────────────────────────────────────────────────────
    # Передача
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, float)
    def send_setpoint_packet(self, install_type: str, param_name: str, value: float):
        try:
            packet = make_setpoint_packet(install_type, param_name, value)
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART TX] Ошибка уставки: {e}")
            return

        hex_str = self._send(packet)
        self.logMessage.emit(
            f"[UART TX] УСТАВКА {install_type.upper()} {param_name}={value:.2f} | {hex_str}"
        )

    @pyqtSlot(str, str, bool)
    def send_command_packet(self, install_type: str, command_name: str, state: bool):
        try:
            packet = make_command_packet(install_type, command_name, state)
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART TX] Ошибка команды: {e}")
            return

        hex_str = self._send(packet)
        self.logMessage.emit(
            f"[UART TX] КОМАНДА {install_type.upper()} {command_name}={'ON' if state else 'OFF'} | {hex_str}"
        )

    def _send(self, packet: bytes) -> str:
        hex_str = packet_to_hex(packet)
        if self._port and self._port.is_open:
            try:
                self._port.write(packet)
            except Exception as e:
                self.logMessage.emit(f"[UART] Ошибка записи: {e}")
        return hex_str

    # ─────────────────────────────────────────────────────────────
    # Приём
    # ─────────────────────────────────────────────────────────────

    def _poll_port(self):
        if not self._port or not self._port.is_open:
            return

        try:
            chunk = self._port.read(self._port.in_waiting or 1)
        except Exception as e:
            self.logMessage.emit(f"[UART RX] Ошибка чтения: {e}")
            return

        if not chunk:
            return

        self._rx_buf.extend(chunk)

        while True:
            packet = find_packet_in_buffer(self._rx_buf)
            if packet is None:
                return
            self._handle_rx_packet(packet)

    def _handle_rx_packet(self, packet: bytes):
        hex_str = packet_to_hex(packet)

        if len(packet) != PACKET_LEN:
            self.logMessage.emit(f"[UART RX] Неверная длина пакета | {hex_str}")
            return

        try:
            install_type, code, _value = parse_float_packet(packet)
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART RX] {e} | {hex_str}")
            return

        self._mark_rx(install_type)
        packet_kind = classify_packet_code(code)

        if packet_kind == "current":
            try:
                install_type, param_name, value = parse_current_value_packet(packet)
            except UartProtocolError as e:
                self.logMessage.emit(f"[UART RX] {e} | {hex_str}")
                return

            self.currentValueChanged.emit(install_type, param_name, value)
            self.logMessage.emit(
                f"[UART RX] ТЕКУЩЕЕ {install_type.upper()} {param_name}={value:.2f} | {hex_str}"
            )
            return

        if packet_kind == "error":
            try:
                install_type, has_error, message, error_name = parse_error_packet(packet)
            except UartProtocolError as e:
                self.logMessage.emit(f"[UART RX] {e} | {hex_str}")
                return

            self.errorStateChanged.emit(install_type, has_error, message)
            self.logMessage.emit(
                f"[UART RX] ОШИБКА {install_type.upper()} {error_name}={'ON' if has_error else 'OFF'} | {hex_str}"
            )
            return

        self.logMessage.emit(f"[UART RX] Неизвестный тип пакета | {hex_str}")

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
            self.logMessage.emit(f"[UART] Связь восстановлена: {install_type.upper()}")
        else:
            self.logMessage.emit(f"[UART] Нет связи: {install_type.upper()}")

    def _check_link_watchdog(self):
        now = QtCore.QDateTime.currentMSecsSinceEpoch()

        for install in INSTALL_TYPES:
            last_rx = self._last_rx_ms.get(install, 0)
            if last_rx <= 0:
                self._set_link_state(install, False)
                continue

            self._set_link_state(install, now - last_rx <= UART_LINK_TIMEOUT_MS)
