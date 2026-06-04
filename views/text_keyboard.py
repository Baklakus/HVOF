"""
views/text_keyboard.py

Экранная текстовая клавиатура.

Это View-компонент.
Он только показывает диалог ввода текста и отдаёт результат через сигнал textEntered.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal


class TextKeyboard(QtWidgets.QDialog):
    textEntered = pyqtSignal(str)

    def __init__(self, parent=None, current_text=""):
        super().__init__(parent)

        self.setWindowTitle("Введите название")
        self.setModal(True)

        self.line_edit = QtWidgets.QLineEdit(current_text)
        self.line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.line_edit.setReadOnly(True)

        chars = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["Z", "X", "C", "V", "B", "N", "M"],
            [" ", "-", "_", ".", ",", "⌫", "C"],
        ]

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.line_edit)

        grid = QtWidgets.QGridLayout()

        row = 0
        for keys in chars:
            col = 0

            for key in keys:
                btn = QtWidgets.QPushButton(key)
                btn.setFixedSize(55, 45)

                if key == "⌫":
                    btn.clicked.connect(self.on_backspace)
                elif key == "C":
                    btn.clicked.connect(self.on_clear)
                else:
                    btn.clicked.connect(
                        lambda _checked=False, k=key: self.on_char(k)
                    )

                grid.addWidget(btn, row, col)
                col += 1

            row += 1

        layout.addLayout(grid)

        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_ok.setFixedHeight(50)
        self.btn_ok.clicked.connect(self.on_ok)
        layout.addWidget(self.btn_ok)

    def on_char(self, char: str):
        self.line_edit.setText(self.line_edit.text() + char)

    def on_backspace(self):
        text = self.line_edit.text()

        if text:
            self.line_edit.setText(text[:-1])

    def on_clear(self):
        self.line_edit.clear()

    def on_ok(self):
        self.textEntered.emit(self.line_edit.text())
        self.accept()