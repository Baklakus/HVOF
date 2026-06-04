"""
models/hvof_data_manager.py

Слой Model / DataManager для HMI HVoF.

Этот класс отвечает только за обмен с МК / эмулятором:
- открытие COM-порта;
- отправка уставок;
- отправка команд;
- приём текущих значений;
- проверка CRC;
- выдача сигналов наверх во ViewModel.

"""

try:
    import serial as _serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from utils.constants import (
    SERIAL_PORT,
    SERIAL_BAUD,
    SERIAL_TIMEOUT_SEC,
    UART_POLL_INTERVAL_MS,
)

from utils.uart_protocol import (
    PACKET_LEN,
    UartProtocolError,
    find_packet_in_buffer,
    make_setpoint_packet,
    make_command_packet,
    parse_current_value_packet,
    packet_to_hex,
)


class HvofDataManager(QObject):
    """
    DataManager для обмена с МК/эмулятором.

    Раньше эта логика находилась в main.py в классе SerialWorker.
    Теперь она вынесена отдельно, согласно архитектуре:
        models -> работа с данными и внешними устройствами
        viewmodels -> логика экрана
        views -> UI
    """

    logMessage = pyqtSignal(str)

    # Текущее значение от МК/эмулятора:
    # install_type: "wire" / "powder"
    # param_name: "propane" / "oxygen" / "air" / "feeder" / "pistol"
    # value: float
    currentValueChanged = pyqtSignal(str, str, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._port = None
        self._rx_buf = bytearray()
        self._rx_timer = None

    # ─────────────────────────────────────────────────────────────
    # Открытие / закрытие порта
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def open_port(self):
        """
        Открывает COM-порт и запускает таймер опроса UART.

        Метод вызывается из main.py после переноса объекта в QThread:
            uart_thread.started.connect(data_manager.open_port)
        """
        if not _SERIAL_AVAILABLE:
            self.logMessage.emit("[UART] pyserial не установлен — режим лога")
            return

        if not SERIAL_PORT:
            self.logMessage.emit("[UART] SERIAL_PORT = None — режим лога")
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

            self.logMessage.emit(
                f"[UART] Порт открыт: {SERIAL_PORT} @ {SERIAL_BAUD}"
            )

            self._rx_timer = QtCore.QTimer(self)
            self._rx_timer.setInterval(UART_POLL_INTERVAL_MS)
            self._rx_timer.timeout.connect(self._poll_port)
            self._rx_timer.start()

        except Exception as e:
            self._port = None
            self.logMessage.emit(f"[UART] Ошибка порта {SERIAL_PORT}: {e}")

    @pyqtSlot()
    def close_port(self):
        """
        Останавливает таймер и закрывает COM-порт.
        Вызывается при завершении приложения.
        """
        if self._rx_timer is not None:
            self._rx_timer.stop()
            self._rx_timer.deleteLater()
            self._rx_timer = None

        if self._port is not None:
            try:
                if self._port.is_open:
                    self._port.close()
                    self.logMessage.emit("[UART] Порт закрыт")
            except Exception as e:
                self.logMessage.emit(f"[UART] Ошибка закрытия порта: {e}")

            self._port = None

        self._rx_buf.clear()

    # ─────────────────────────────────────────────────────────────
    # Отправка данных в МК / эмулятор
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, float)
    def send_setpoint_packet(self, install_type: str, param_name: str, value: float):
        """
        Отправляет уставку.

        Это адаптация старого метода SerialWorker.send_setpoint_packet().
        """
        try:
            packet = make_setpoint_packet(
                install=install_type,
                param_name=param_name,
                value=value,
            )
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART TX] Ошибка уставки: {e}")
            return

        hex_str = self._send(packet)

        self.logMessage.emit(
            f"[UART TX] УСТАВКА {install_type.upper()} "
            f"{param_name}={value:.2f} | {hex_str}"
        )

    @pyqtSlot(str, str, bool)
    def send_command_packet(self, install_type: str, command_name: str, state: bool):
        """
        Отправляет команду включения/выключения.

        Это адаптация старого метода SerialWorker.send_command_packet().
        """
        try:
            packet = make_command_packet(
                install=install_type,
                command_name=command_name,
                state=state,
            )
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART TX] Ошибка команды: {e}")
            return

        hex_str = self._send(packet)

        self.logMessage.emit(
            f"[UART TX] КОМАНДА {install_type.upper()} "
            f"{command_name}={'ON' if state else 'OFF'} | {hex_str}"
        )

    def _send(self, packet: bytes) -> str:
        """
        Отправляет сырой пакет в COM-порт.
        Возвращает HEX-строку для логов.
        """
        hex_str = packet_to_hex(packet)

        if self._port and self._port.is_open:
            try:
                self._port.write(packet)
            except Exception as e:
                self.logMessage.emit(f"[UART] Ошибка записи: {e}")

        return hex_str

    # ─────────────────────────────────────────────────────────────
    # Приём данных от МК / эмулятора
    # ─────────────────────────────────────────────────────────────

    def _poll_port(self):
        """
        Опрос COM-порта.

        Таймер работает внутри UART-потока, поэтому GUI не блокируется.
        """
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
        """
        Обрабатывает один входящий пакет.

        Сейчас входящие пакеты считаем текущими значениями параметров:
            AA + install + param + float + CRC16

        Такой же формат отправляет наш emulator.py.
        """
        hex_str = packet_to_hex(packet)

        if len(packet) != PACKET_LEN:
            self.logMessage.emit(f"[UART RX] Неверная длина пакета | {hex_str}")
            return

        try:
            install_type, param_name, value = parse_current_value_packet(packet)
        except UartProtocolError as e:
            self.logMessage.emit(f"[UART RX] {e} | {hex_str}")
            return

        self.currentValueChanged.emit(install_type, param_name, value)

        self.logMessage.emit(
            f"[UART RX] ТЕКУЩЕЕ {install_type.upper()} "
            f"{param_name}={value:.2f} | {hex_str}"
        )