"""
viewmodels/recipe_view_model.py

ViewModel окна рецептов HMI HVoF.

Этот класс отвечает за:
- текущую выбранную установку: wire / powder;
- отдельный выбранный индекс рецепта для каждой установки;
- загрузку таблицы рецептов;
- выбор строки;
- перемещение выбора вверх / вниз;
- редактирование ячейки рецепта;
- добавление нового рецепта;
- применение выбранного рецепта.

UI-кода здесь быть не должно.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_TYPES,
    INSTALL_TITLES,
)

from models.recipe_storage import RecipeStorage


class RecipeViewModel(QObject):
    """
    ViewModel таблицы рецептов.

    Раньше этот класс находился внутри большого main.py.
    Теперь он вынесен в отдельный файл согласно архитектуре:

        viewmodels/recipe_view_model.py
    """

    # Передаёт во View список рецептов текущей установки
    tableDataChanged = pyqtSignal(list)

    # Передаёт во View индекс выбранной строки
    selectedIndexChanged = pyqtSignal(int)

    # Передаёт выбранный рецепт в MainViewModel
    modeApplied = pyqtSignal(dict)

    # Заголовок таблицы рецептов: "Рецепты — ПРОВОЛОКА" / "Рецепты — ПОРОШОК"
    titleChanged = pyqtSignal(str)

    def __init__(self, storage: RecipeStorage):
        super().__init__()

        self.storage = storage

        self.current_install = INSTALL_WIRE

        # Храним отдельную выбранную строку для проволоки и порошка.
        self.current_indices = {
            install: 0
            for install in INSTALL_TYPES
        }

    @property
    def current_index(self) -> int:
        return self.current_indices[self.current_install]

    @current_index.setter
    def current_index(self, value: int):
        self.current_indices[self.current_install] = value

    def _rows(self) -> list[dict]:
        """
        Возвращает рецепты текущей выбранной установки.
        """
        return self.storage.get_recipes(self.current_install)

    def load_recipes(self):
        """
        Загружает рецепты текущей установки и отправляет их во View.
        """
        rows = self._rows()

        if rows:
            self.current_index = max(
                0,
                min(self.current_index, len(rows) - 1),
            )
        else:
            self.current_index = -1

        self.titleChanged.emit(
            f"Рецепты — {INSTALL_TITLES[self.current_install]}"
        )

        self.tableDataChanged.emit(rows)
        self.selectedIndexChanged.emit(self.current_index)

    @pyqtSlot(str)
    def set_installation(self, install_type: str):
        """
        Переключает таблицу рецептов при выборе установки:
        - wire
        - powder
        """
        if install_type not in INSTALL_TYPES:
            return

        if install_type == self.current_install:
            self.load_recipes()
            return

        self.current_install = install_type
        self.load_recipes()

    @pyqtSlot(int)
    def select_row(self, index: int):
        """
        Выбирает строку рецепта.
        """
        rows = self._rows()

        if 0 <= index < len(rows):
            self.current_index = index
            self.selectedIndexChanged.emit(index)

    @pyqtSlot()
    def move_up(self):
        """
        Перемещает выбор рецепта вверх.
        """
        if self.current_index > 0:
            self.current_index -= 1
            self.selectedIndexChanged.emit(self.current_index)

    @pyqtSlot()
    def move_down(self):
        """
        Перемещает выбор рецепта вниз.
        """
        rows = self._rows()

        if self.current_index < len(rows) - 1:
            self.current_index += 1
            self.selectedIndexChanged.emit(self.current_index)

    @pyqtSlot(int, int, object)
    def update_cell(self, row: int, col: int, value):
        """
        Обновляет одну ячейку рецепта.

        row:
            индекс строки

        col:
            индекс колонки в QTableWidget:
            0 -> number, не редактируется
            1 -> name
            2 -> propane
            3 -> oxygen
            4 -> feeder_speed

        value:
            новое значение
        """
        self.storage.update_recipe(
            self.current_install,
            row,
            col,
            value,
        )

        self.tableDataChanged.emit(self._rows())
        self.selectedIndexChanged.emit(self.current_index)

    @pyqtSlot()
    def apply_selected(self):
        """
        Применяет выбранный рецепт.

        Само применение уставок выполняет MainViewModel.
        Здесь мы только отправляем выбранный recipe через сигнал modeApplied.
        """
        rows = self._rows()

        if 0 <= self.current_index < len(rows):
            recipe = rows[self.current_index].copy()
            recipe["install"] = self.current_install

            self.modeApplied.emit(recipe)

    @pyqtSlot()
    def add_recipe(self):
        """
        Добавляет новый рецепт в текущую таблицу.
        """
        index = self.storage.add_recipe(self.current_install)

        self.tableDataChanged.emit(self._rows())
        self.select_row(index)