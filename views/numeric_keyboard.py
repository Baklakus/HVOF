"""
views/numeric_keyboard.py

Экранная числовая клавиатура.

Это View-компонент.
Он только показывает диалог ввода числа и отдаёт результат через сигнал valueEntered.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal


class NumericKeyboard(QtWidgets.QDialog):
    valueEntered = pyqtSignal(float)

    def __init__(self, parent=None, current_value=0.0):
        super().__init__(parent)

        self.setWindowTitle("Введите число")
        self.setModal(True)

        self.line_edit = QtWidgets.QLineEdit(str(current_value))
        self.line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.line_edit.setReadOnly(True)

        grid = QtWidgets.QGridLayout()

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
            btn.setFixedSize(60, 60)

            if text == "⌫":
                btn.clicked.connect(self.on_backspace)
            else:
                btn.clicked.connect(
                    lambda _checked=False, t=text: self.on_button_clicked(t)
                )

            grid.addWidget(btn, row, col)

        btn_clear = QtWidgets.QPushButton("C")
        btn_clear.setFixedSize(60, 60)
        btn_clear.clicked.connect(self.on_clear)
        grid.addWidget(btn_clear, 4, 0)

        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_ok.setFixedHeight(50)
        self.btn_ok.clicked.connect(self.on_ok)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.line_edit)
        layout.addLayout(grid)
        layout.addWidget(self.btn_ok)

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