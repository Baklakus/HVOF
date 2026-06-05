"""
views/startup_params_dialog.py

Диалог редактирования параметров запуска установки.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSlot

from utils.constants import (
    STARTUP_PARAM_TITLES,
    STARTUP_PARAM_UNITS,
)

from views.numeric_keyboard import NumericKeyboard


class StartupParamsDialog(QtWidgets.QDialog):
    def __init__(self, startup_vm, parent=None):
        super().__init__(parent)

        self.startup_vm = startup_vm
        self._labels: dict[str, QtWidgets.QLabel] = {}

        self.setWindowTitle("Параметры запуска")
        self.setModal(True)
        self.resize(560, 560)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #101828;
            }

            QLabel {
                color: #FFFFFF;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 18px;
            }

            QLabel[paramValue="true"] {
                background-color: #364153;
                border-radius: 8px;
                padding: 8px;
                color: #FFFFFF;
                font-size: 20px;
            }

            QLabel[paramUnit="true"] {
                color: #818181;
                font-size: 16px;
            }

            QPushButton {
                background-color: #334155;
                color: #FFFFFF;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 10px;
                font-size: 16px;
            }

            QPushButton:hover {
                background-color: #475569;
            }

            QPushButton:pressed {
                background-color: #1E2939;
            }

            QPushButton#btnClose {
                background-color: #22C55E;
                border: none;
            }

            QPushButton#btnReset {
                background-color: #EF4444;
                border: none;
            }

            QLabel#lblHint {
                color: #818181;
                font-size: 14px;
            }
            """
        )

        self.lblTitle = QtWidgets.QLabel("Параметры запуска")
        self.lblTitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lblTitle.setStyleSheet("font-size: 24px; font-weight: 500;")

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        row = 0

        for key, title in STARTUP_PARAM_TITLES.items():
            name_label = QtWidgets.QLabel(title)

            value_label = QtWidgets.QLabel("0.0")
            value_label.setProperty("paramValue", True)
            value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            value_label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            value_label.setToolTip("Нажмите для ввода значения")

            unit_label = QtWidgets.QLabel(STARTUP_PARAM_UNITS.get(key, ""))
            unit_label.setProperty("paramUnit", True)

            value_label.mousePressEvent = (
                lambda event, k=key: self._open_keyboard(k)
            )

            self._labels[key] = value_label

            form.addWidget(name_label, row, 0)
            form.addWidget(value_label, row, 1)
            form.addWidget(unit_label, row, 2)

            row += 1

        self.lblHint = QtWidgets.QLabel(
            "Нажмите на значение, чтобы открыть экранную клавиатуру"
        )
        self.lblHint.setObjectName("lblHint")
        self.lblHint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.btnReset = QtWidgets.QPushButton("Сбросить")
        self.btnReset.setObjectName("btnReset")
        self.btnReset.clicked.connect(self.startup_vm.reset_current_to_defaults)

        self.btnClose = QtWidgets.QPushButton("Закрыть")
        self.btnClose.setObjectName("btnClose")
        self.btnClose.clicked.connect(self.accept)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.btnReset)
        buttons.addWidget(self.btnClose)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.lblTitle)
        layout.addSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.lblHint)
        layout.addStretch()
        layout.addLayout(buttons)

        self.startup_vm.titleChanged.connect(self.lblTitle.setText)
        self.startup_vm.paramsChanged.connect(self._on_params_changed)

        self.startup_vm.load_params()

    @pyqtSlot(dict)
    def _on_params_changed(self, params: dict):
        for key, label in self._labels.items():
            value = float(params.get(key, 0.0))
            label.setText(f"{value:.1f}")

    def _open_keyboard(self, key: str):
        current_text = self._labels[key].text()

        try:
            current_value = float(current_text)
        except ValueError:
            current_value = 0.0

        dlg = NumericKeyboard(self, current_value)

        dlg.valueEntered.connect(
            lambda value, k=key: self.startup_vm.update_param(k, value)
        )

        dlg.exec()