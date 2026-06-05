"""
main.py

Точка входа приложения HMI HVoF.
"""

import sys

from PyQt6 import QtWidgets, QtCore

import resources_rc

from models.hvof_data_manager import HvofDataManager
from models.recipe_storage import RecipeStorage
from models.startup_params_storage import StartupParamsStorage

from viewmodels.main_view_model import MainViewModel
from viewmodels.recipe_view_model import RecipeViewModel
from viewmodels.startup_params_view_model import StartupParamsViewModel

from views.main_window import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)

    # ─────────────────────────────────────────────────────────────
    # Model
    # ─────────────────────────────────────────────────────────────

    data_manager = HvofDataManager()
    recipe_storage = RecipeStorage()
    startup_storage = StartupParamsStorage()

    # ─────────────────────────────────────────────────────────────
    # ViewModel
    # ─────────────────────────────────────────────────────────────

    main_vm = MainViewModel()
    recipe_vm = RecipeViewModel(recipe_storage)
    startup_vm = StartupParamsViewModel(startup_storage)

    # ─────────────────────────────────────────────────────────────
    # UART-поток
    # ─────────────────────────────────────────────────────────────

    uart_thread = QtCore.QThread()
    data_manager.moveToThread(uart_thread)

    uart_thread.started.connect(data_manager.open_port)

    # ─────────────────────────────────────────────────────────────
    # MainViewModel -> DataManager
    # ─────────────────────────────────────────────────────────────

    main_vm.requestPacketSend.connect(data_manager.send_setpoint_packet)
    main_vm.requestCommandSend.connect(data_manager.send_command_packet)

    # ─────────────────────────────────────────────────────────────
    # DataManager -> MainViewModel
    # ─────────────────────────────────────────────────────────────

    data_manager.currentValueChanged.connect(main_vm.update_current_value)

    if hasattr(data_manager, "errorStateChanged"):
        data_manager.errorStateChanged.connect(main_vm.update_error_state)

    if hasattr(data_manager, "linkStateChanged"):
        data_manager.linkStateChanged.connect(main_vm.update_link_state)

    data_manager.logMessage.connect(lambda message: print(message, flush=True))

    # ─────────────────────────────────────────────────────────────
    # RecipeViewModel -> MainViewModel
    # ─────────────────────────────────────────────────────────────

    recipe_vm.modeApplied.connect(main_vm.apply_recipe)

    # ─────────────────────────────────────────────────────────────
    # StartupParamsViewModel -> MainViewModel
    # ─────────────────────────────────────────────────────────────

    main_vm.installationChanged.connect(startup_vm.set_installation)
    startup_vm.paramsChanged.connect(main_vm.set_startup_params)

    # Первичная загрузка параметров запуска.
    startup_vm.load_params()

    # ─────────────────────────────────────────────────────────────
    # View
    # ─────────────────────────────────────────────────────────────

    window = MainWindow(main_vm, recipe_vm, startup_vm)
    window.show()

    # Запускаем UART после создания всех связей.
    uart_thread.start()

    # ─────────────────────────────────────────────────────────────
    # Запуск приложения
    # ─────────────────────────────────────────────────────────────

    exit_code = app.exec()

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