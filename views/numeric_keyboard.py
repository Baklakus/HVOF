"""
views/numeric_keyboard.py

Стандартная экранная числовая клавиатура HMI.
Используется и для рабочих параметров, и для параметров запуска.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal


class NumericKeyboard(QtWidgets.QDialog):
    valueEntered = pyqtSignal(float)

    def __init__(self, parent=None, current_value=0.0):
        super().__init__(parent)

        self.setWindowTitle("Введите число")
        self.setModal(True)
        self.resize(360, 520)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #101828;
                border-radius: 16px;
            }

            QLineEdit {
                background-color: #1E2939;
                color: #FFFFFF;
                border: 1px solid #364153;
                border-radius: 12px;
                padding: 12px;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 32px;
                font-weight: 500;
            }

            QPushButton {
                background-color: #1E2939;
                color: #FFFFFF;
                border: 1px solid #364153;
                border-radius: 14px;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 26px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #334155;
            }

            QPushButton:pressed {
                background-color: #475569;
            }

            QPushButton#btnOk {
                background-color: #1477F8;
                border: none;
                font-size: 22px;
                font-weight: 600;
            }

            QPushButton#btnOk:hover {
                background-color: #2563EB;
            }

            QPushButton#btnClear {
                background-color: #EF4444;
                border: none;
            }

            QPushButton#btnBackspace {
                background-color: #334155;
            }
            """
        )

        self.line_edit = QtWidgets.QLineEdit(str(current_value))
        self.line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.line_edit.setReadOnly(True)
        self.line_edit.setMinimumHeight(70)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        buttons = [
            ("7", 0, 0),
            ("8", 0, 1),
            ("9", 0, 2),
            ("4", 1, 0),
            ("5", 1, 1),
            ("6", 1, 2),
            ("1", 2, 0),
            ("2", 2, 1),
            ("3", 2, 2),
            ("0", 3, 0),
            (".", 3, 1),
            ("⌫", 3, 2),
        ]

        for text, row, col in buttons:
            btn = QtWidgets.QPushButton(text)
            btn.setMinimumSize(90, 70)

            if text == "⌫":
                btn.setObjectName("btnBackspace")
                btn.clicked.connect(self.on_backspace)
            else:
                btn.clicked.connect(
                    lambda _checked=False, t=text: self.on_button_clicked(t)
                )

            grid.addWidget(btn, row, col)

        btn_clear = QtWidgets.QPushButton("C")
        btn_clear.setObjectName("btnClear")
        btn_clear.setMinimumSize(90, 70)
        btn_clear.clicked.connect(self.on_clear)
        grid.addWidget(btn_clear, 4, 0)

        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_ok.setObjectName("btnOk")
        self.btn_ok.setMinimumHeight(70)
        self.btn_ok.clicked.connect(self.on_ok)
        grid.addWidget(self.btn_ok, 4, 1, 1, 2)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        layout.addWidget(self.line_edit)
        layout.addLayout(grid)

    def on_button_clicked(self, char: str):
        text = self.line_edit.text()

        if char == "." and "." in text:
            return

        if text == "0" and char != ".":
            self.line_edit.setText(char)
            return

        self.line_edit.setText(text + char)

    def on_backspace(self):
        text = self.line_edit.text()

        if text:
            self.line_edit.setText(text[:-1])

    def on_clear(self):
        self.line_edit.clear()

    def on_ok(self):
        try:
            value = float(self.line_edit.text())
        except ValueError:
            return

        self.valueEntered.emit(value)
        self.accept()