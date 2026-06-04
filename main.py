"""
main.py

Точка входа приложения HMI HVoF.

После разделения большого main.py этот файл должен только:
- создать QApplication;
- создать Model / DataManager;
- создать ViewModel;
- создать View;
- соединить сигналы между слоями;
- запустить UART-поток;
- показать главное окно.
"""

import sys

from PyQt6 import QtWidgets, QtCore

try:
    import resources_rc  # noqa: F401
except ImportError:
    pass

from models.hvof_data_manager import HvofDataManager
from models.recipe_storage import RecipeStorage

from viewmodels.main_view_model import MainViewModel
from viewmodels.recipe_view_model import RecipeViewModel

from views.main_window import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)

    # ─────────────────────────────────────────────────────────────
    # Model
    # ─────────────────────────────────────────────────────────────

    data_manager = HvofDataManager()
    recipe_storage = RecipeStorage()

    # ─────────────────────────────────────────────────────────────
    # ViewModel
    # ─────────────────────────────────────────────────────────────

    main_vm = MainViewModel()
    recipe_vm = RecipeViewModel(recipe_storage)

    # ─────────────────────────────────────────────────────────────
    # UART-поток
    # ─────────────────────────────────────────────────────────────

    uart_thread = QtCore.QThread()
    data_manager.moveToThread(uart_thread)

    uart_thread.started.connect(data_manager.open_port)

    # ─────────────────────────────────────────────────────────────
    # Связь ViewModel -> DataManager
    # ─────────────────────────────────────────────────────────────

    main_vm.requestPacketSend.connect(data_manager.send_setpoint_packet)
    main_vm.requestCommandSend.connect(data_manager.send_command_packet)

    # ─────────────────────────────────────────────────────────────
    # Связь DataManager -> ViewModel
    # ─────────────────────────────────────────────────────────────

    data_manager.currentValueChanged.connect(main_vm.update_current_value)
    data_manager.logMessage.connect(lambda message: print(message, flush=True))

    # ─────────────────────────────────────────────────────────────
    # Связь RecipeViewModel -> MainViewModel
    # ─────────────────────────────────────────────────────────────

    recipe_vm.modeApplied.connect(main_vm.apply_recipe)

    # ─────────────────────────────────────────────────────────────
    # View
    # ─────────────────────────────────────────────────────────────

    window = MainWindow(main_vm, recipe_vm)
    window.show()

    # Запускаем UART после создания всех связей.
    uart_thread.start()

    # ─────────────────────────────────────────────────────────────
    # Запуск приложения
    # ─────────────────────────────────────────────────────────────

    exit_code = app.exec()

    # ─────────────────────────────────────────────────────────────
    # Корректное завершение UART-потока
    # ─────────────────────────────────────────────────────────────

    if uart_thread.isRunning():
        QtCore.QMetaObject.invokeMethod(
            data_manager,
            "close_port",
            QtCore.Qt.ConnectionType.BlockingQueuedConnection,
        )

        uart_thread.quit()
        uart_thread.wait(3000)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()