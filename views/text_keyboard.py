"""
views/text_keyboard.py

Стандартная экранная текстовая клавиатура HMI.
Используется для редактирования названий рецептов / материалов.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal


class TextKeyboard(QtWidgets.QDialog):
    textEntered = pyqtSignal(str)

    def __init__(self, parent=None, current_text=""):
        super().__init__(parent)

        self.setWindowTitle("Введите текст")
        self.setModal(True)
        self.resize(820, 520)

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
                font-size: 28px;
                font-weight: 500;
            }

            QPushButton {
                background-color: #1E2939;
                color: #FFFFFF;
                border: 1px solid #364153;
                border-radius: 14px;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 22px;
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
                font-weight: 600;
            }

            QPushButton#btnBackspace {
                background-color: #334155;
                font-weight: 600;
            }

            QPushButton#btnSpace {
                background-color: #334155;
            }

            QPushButton#btnLang {
                background-color: #334155;
                font-size: 18px;
            }
            """
        )

        self._is_russian = True
        self._is_upper = True

        self.line_edit = QtWidgets.QLineEdit(current_text)
        self.line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.line_edit.setReadOnly(True)
        self.line_edit.setMinimumHeight(68)

        self.keyboard_layout = QtWidgets.QVBoxLayout()
        self.keyboard_layout.setSpacing(10)

        self._build_keyboard()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        layout.addWidget(self.line_edit)
        layout.addLayout(self.keyboard_layout)

    def _clear_keyboard_layout(self):
        while self.keyboard_layout.count():
            item = self.keyboard_layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_nested_layout(item.layout())

    def _clear_nested_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_nested_layout(item.layout())

    def _build_keyboard(self):
        self._clear_keyboard_layout()

        if self._is_russian:
            rows = [
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
                ["Й", "Ц", "У", "К", "Е", "Н", "Г", "Ш", "Щ", "З", "Х"],
                ["Ф", "Ы", "В", "А", "П", "Р", "О", "Л", "Д", "Ж", "Э"],
                ["Я", "Ч", "С", "М", "И", "Т", "Ь", "Б", "Ю"],
            ]
        else:
            rows = [
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
                ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
                ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
                ["Z", "X", "C", "V", "B", "N", "M"],
            ]

        for row_keys in rows:
            row_layout = QtWidgets.QHBoxLayout()
            row_layout.setSpacing(8)

            row_layout.addStretch()

            for key in row_keys:
                button = self._make_key_button(key)
                row_layout.addWidget(button)

            row_layout.addStretch()
            self.keyboard_layout.addLayout(row_layout)

        service_row = QtWidgets.QHBoxLayout()
        service_row.setSpacing(8)

        btn_lang = self._make_service_button("RU/EN", "btnLang")
        btn_lang.clicked.connect(self._toggle_language)

        btn_case = self._make_service_button("Aa", "btnLang")
        btn_case.clicked.connect(self._toggle_case)

        btn_dash = self._make_key_button("-")
        btn_dot = self._make_key_button(".")
        btn_comma = self._make_key_button(",")

        btn_space = self._make_service_button("Пробел", "btnSpace")
        btn_space.clicked.connect(lambda: self._append_text(" "))

        btn_backspace = self._make_service_button("⌫", "btnBackspace")
        btn_backspace.clicked.connect(self.on_backspace)

        btn_clear = self._make_service_button("C", "btnClear")
        btn_clear.clicked.connect(self.on_clear)

        btn_ok = self._make_service_button("OK", "btnOk")
        btn_ok.clicked.connect(self.on_ok)

        service_row.addWidget(btn_lang)
        service_row.addWidget(btn_case)
        service_row.addWidget(btn_dash)
        service_row.addWidget(btn_dot)
        service_row.addWidget(btn_comma)
        service_row.addWidget(btn_space, 3)
        service_row.addWidget(btn_backspace)
        service_row.addWidget(btn_clear)
        service_row.addWidget(btn_ok, 2)

        self.keyboard_layout.addLayout(service_row)

    def _make_key_button(self, text: str) -> QtWidgets.QPushButton:
        button_text = text if self._is_upper else text.lower()

        button = QtWidgets.QPushButton(button_text)
        button.setMinimumSize(58, 58)
        button.clicked.connect(
            lambda _checked=False, t=button_text: self._append_text(t)
        )

        return button

    def _make_service_button(self, text: str, object_name: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        button.setObjectName(object_name)
        button.setMinimumHeight(58)
        button.setMinimumWidth(74)

        return button

    def _append_text(self, text: str):
        self.line_edit.setText(self.line_edit.text() + text)

    def _toggle_language(self):
        self._is_russian = not self._is_russian
        self._build_keyboard()

    def _toggle_case(self):
        self._is_upper = not self._is_upper
        self._build_keyboard()

    def on_backspace(self):
        text = self.line_edit.text()

        if text:
            self.line_edit.setText(text[:-1])

    def on_clear(self):
        self.line_edit.clear()

    def on_ok(self):
        self.textEntered.emit(self.line_edit.text())
        self.accept()