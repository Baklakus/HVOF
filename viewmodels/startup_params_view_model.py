"""
viewmodels/startup_params_view_model.py

ViewModel параметров запуска.

Отвечает за:
- текущую выбранную установку;
- загрузку параметров запуска;
- изменение параметров запуска;
- передачу параметров запуска в MainViewModel.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_TYPES,
    INSTALL_TITLES,
)

from models.startup_params_storage import StartupParamsStorage


class StartupParamsViewModel(QObject):
    paramsChanged = pyqtSignal(dict)
    titleChanged = pyqtSignal(str)

    def __init__(self, storage: StartupParamsStorage):
        super().__init__()

        self.storage = storage
        self.current_install = INSTALL_WIRE

    def _params(self) -> dict:
        return self.storage.get_params(self.current_install)

    def load_params(self):
        self.titleChanged.emit(
            f"Параметры запуска — {INSTALL_TITLES[self.current_install]}"
        )
        self.paramsChanged.emit(self._params().copy())

    @pyqtSlot(str)
    def set_installation(self, install_type: str):
        if install_type not in INSTALL_TYPES:
            return

        self.current_install = install_type
        self.load_params()

    @pyqtSlot(str, float)
    def update_param(self, key: str, value: float):
        self.storage.update_param(
            self.current_install,
            key,
            value,
        )

        self.load_params()

    @pyqtSlot()
    def reset_current_to_defaults(self):
        self.storage.reset_to_defaults(self.current_install)
        self.load_params()