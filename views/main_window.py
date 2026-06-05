"""
views/main_window.py

View главного окна HMI HVoF.

Этот файл отвечает только за UI:
- setupUi;
- соединение кнопок с ViewModel;
- отображение значений в QLabel;
- заполнение таблицы рецептов;
- открытие экранных клавиатур.

UART, рецепты и бизнес-логика здесь не хранятся.
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSlot
from views.startup_params_dialog import StartupParamsDialog
from start_window_ui import Ui_MainWindow

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_POWDER,
    RECIPE_COLUMNS,
    RECIPE_HEADERS,
    RECIPE_NUMERIC_COLUMNS,
)

from views.numeric_keyboard import NumericKeyboard
from views.text_keyboard import TextKeyboard


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, vm, recipe_vm, startup_vm):
        super().__init__()

        self.vm = vm
        self.recipe_vm = recipe_vm
        self.startup_vm = startup_vm

        self.setupUi(self)

        self.stackedWidget.setCurrentIndex(0)

        self._patch_topbar_icons()
        self._create_topbar_recipes_button()
        self._connect_all()
        self._setup_recipes_ui()
        self._setup_parameter_keyboards()

    # ─────────────────────────────────────────────────────────────
    # Верхняя панель
    # ─────────────────────────────────────────────────────────────

    def _patch_topbar_icons(self):
        replacements = {
            "btnTopSwitch": "↔",
            "btnTopBack": "←",
            "btnTopSettings": "⚙",
            "btnTopHome": "⌂",
        }

        for name, symbol in replacements.items():
            btn = getattr(self, name, None)

            if btn and (not btn.icon() or btn.icon().isNull()):
                btn.setText(symbol)

    def _create_topbar_recipes_button(self):
        """
        Создаёт отдельную кнопку перехода к рецептам в верхней панели.

        btnTopSwitch визуально является кнопкой питания,
        поэтому его нельзя использовать для рецептов.
        """
        if hasattr(self, "btnTopRecipes"):
            return

        self.btnTopRecipes = QtWidgets.QPushButton(parent=self.frameTopBar)
        self.btnTopRecipes.setObjectName("btnTopRecipes")
        self.btnTopRecipes.setText("Рецепты")
        self.btnTopRecipes.setMinimumSize(QtCore.QSize(110, 44))
        self.btnTopRecipes.setMaximumHeight(44)
        self.btnTopRecipes.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btnTopRecipes.setStyleSheet(
            """
            QPushButton#btnTopRecipes {
                background-color: #334155;
                color: #FFFFFF;
                border: 1px solid #475569;
                border-radius: 8px;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 16px;
                font-weight: 500;
                padding: 6px 12px;
            }

            QPushButton#btnTopRecipes:hover {
                background-color: #475569;
            }

            QPushButton#btnTopRecipes:pressed {
                background-color: #1E2939;
            }
            """
        )

        # Вставляем кнопку рядом с кнопкой настроек.
        index = self.horizontalLayout_18.indexOf(self.btnTopSettings)

        if index >= 0:
            self.horizontalLayout_18.insertWidget(index + 1, self.btnTopRecipes)
        else:
            self.horizontalLayout_18.addWidget(self.btnTopRecipes)
    # ─────────────────────────────────────────────────────────────
    # Подключение сигналов
    # ─────────────────────────────────────────────────────────────

    def _connect_all(self):
        vm = self.vm

        self.btnWire.clicked.connect(lambda: vm.select_installation(INSTALL_WIRE))
        self.btnPowder.clicked.connect(lambda: vm.select_installation(INSTALL_POWDER))
        self.btnExit.clicked.connect(self.request_close)

        if hasattr(self, "btnTopBack"):
            self.btnTopBack.clicked.connect(vm.go_back)

        if hasattr(self, "btnTopHome"):
            self.btnTopHome.clicked.connect(vm.go_back)

        if hasattr(self, "btnTopSwitch"):
            # btnTopSwitch — это кнопка питания
            self.btnTopSwitch.clicked.connect(self.request_close)

        if hasattr(self, "btnTopRecipes"):
            # Отдельная кнопка рецептов
            self.btnTopRecipes.clicked.connect(
                lambda: self.stackedWidget.setCurrentIndex(2)
            )

        if hasattr(self, "btnTopSettings"):
            # Параметры запуска
            self.btnTopSettings.clicked.connect(self._open_startup_params_dialog)
        self.btnStart.clicked.connect(lambda: vm.set_main_system_state(True))
        self.btnStop.clicked.connect(lambda: vm.set_main_system_state(False))

        self.checkBoxArcIgnition.toggled.connect(vm.set_ignition_state)
        self.checkBoxFeedingSystem.toggled.connect(vm.set_feeding_state)

        # Пропан
        self.bntPropaneIncrease.clicked.connect(lambda: vm.on_increment("propane"))
        self.btnPropaneDecrease.clicked.connect(lambda: vm.on_decrement("propane"))
        self.btnPropaneSet.clicked.connect(lambda: vm.commit_setpoint("propane"))
        self.checkBoxPropaneSwitch.toggled.connect(
            lambda state: vm.toggle_node("propane", state)
        )

        # Кислород
        self.bntOxygenIncrease.clicked.connect(lambda: vm.on_increment("oxygen"))
        self.btnOxygenDecrease.clicked.connect(lambda: vm.on_decrement("oxygen"))
        self.btnOxygenSet.clicked.connect(lambda: vm.commit_setpoint("oxygen"))
        self.checkBoxOxygenSwitch.toggled.connect(
            lambda state: vm.toggle_node("oxygen", state)
        )

        # Воздух
        self.bntAirIncrease.clicked.connect(lambda: vm.on_increment("air"))
        self.btnAirDecrease.clicked.connect(lambda: vm.on_decrement("air"))
        self.btnAirSet.clicked.connect(lambda: vm.commit_setpoint("air"))

        if hasattr(self, "checkBoxAirSwitch"):
            self.checkBoxAirSwitch.toggled.connect(
                lambda state: vm.toggle_node("air", state)
            )

        # Подача / Q газа
        self.bntQgas_FeederIncrease.clicked.connect(lambda: vm.on_increment("feeder"))
        self.btnQgas_FeederDecrease.clicked.connect(lambda: vm.on_decrement("feeder"))
        self.btnQgas_FeederSet.clicked.connect(lambda: vm.commit_setpoint("feeder"))
        self.checkBoxQgas_FeederSwitch.toggled.connect(
            lambda state: vm.toggle_node("feeder", state)
        )

        # Пистолет / Питатель
        self.btnPistol_PatatelIncrease.clicked.connect(
            lambda: vm.on_increment("pistol")
        )
        self.btnPistol_PatatelDecrease.clicked.connect(
            lambda: vm.on_decrement("pistol")
        )
        self.btnPistol_PatatelSet.clicked.connect(
            lambda: vm.commit_setpoint("pistol")
        )
        self.checkBoxPistol_PatatelSwitch.toggled.connect(
            lambda state: vm.toggle_node("pistol", state)
        )

        vm.pageChanged.connect(self.stackedWidget.setCurrentIndex)
        vm.valuesChanged.connect(self._on_values_changed)
        vm.currentValuesChanged.connect(self._on_current_values_changed)
        vm.statesChanged.connect(self._on_states_changed)
        vm.modeLabelChanged.connect(self._on_mode_label)
        vm.installationChanged.connect(self.recipe_vm.set_installation)
        vm.currentRecipeChanged.connect(self.lblCurrentMode.setText)
        vm.modeSwitchBlocked.connect(self._on_mode_switch_blocked)
        vm.errorStateChanged.connect(self._on_error_state_changed)
        vm.linkStateChanged.connect(self._on_link_state_changed)

        self.startup_vm.set_installation(self.vm.current_install)

        if hasattr(self, "btnRecipesBack"):
            self.btnRecipesBack.clicked.connect(
                lambda: self.stackedWidget.setCurrentIndex(1)
            )

        # Связь RecipeViewModel -> MainViewModel выполнена в main.py.

    def _setup_parameter_keyboards(self):
        """
        Подключает экранную клавиатуру к рабочим значениям параметров.

        Нажимаем на значение:
            35.0 л/мин

        Открывается NumericKeyboard.
        После ввода число попадает в рабочее значение.
        Отправка в МК выполняется только после нажатия SET.
        """
        label_map = {
            "propane": self.lblPropaneWorkWalue,
            "oxygen": self.lblOxygenWorkWalue,
            "air": self.lblAirWorkWalue,
            "feeder": self.lblQgas_FeederWorkWalue,
            "pistol": self.lblPistol_PatatelWorkWalue,
        }

        for param, label in label_map.items():
            label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            label.setToolTip("Нажмите для ввода значения")

            label.mousePressEvent = (
                lambda event, p=param: self._open_parameter_keyboard(p)
            )

    def _open_parameter_keyboard(self, param: str):
        """
        Открывает числовую клавиатуру для выбранного параметра.
        """
        current_value = self.vm._disp_now().get(param, 0.0)

        dlg = NumericKeyboard(self, current_value)

        dlg.valueEntered.connect(
            lambda value, p=param: self.vm.set_display_value(p, value)
        )

        dlg.exec()

    # ─────────────────────────────────────────────────────────────
    # Рецепты
    # ─────────────────────────────────────────────────────────────

    def _setup_recipes_ui(self):
        rvm = self.recipe_vm

        rvm.tableDataChanged.connect(self._on_recipes_changed)
        rvm.selectedIndexChanged.connect(self._on_recipe_selection_changed)
        rvm.titleChanged.connect(self.lblRecipesTitle.setText)

        rvm.load_recipes()

        if hasattr(self, "btnRecipeUp"):
            self.btnRecipeUp.clicked.connect(rvm.move_up)

        if hasattr(self, "btnRecipeDown"):
            self.btnRecipeDown.clicked.connect(rvm.move_down)

        if hasattr(self, "btnRecipeSelect"):
            self.btnRecipeSelect.clicked.connect(self._apply_selected_recipe)

        if hasattr(self, "btnAddRecipe"):
            self.btnAddRecipe.clicked.connect(rvm.add_recipe)

        self.tableRecipes.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.tableRecipes.cellClicked.connect(
            lambda row, _col: rvm.select_row(row)
        )

        self.tableRecipes.currentCellChanged.connect(
            lambda row, _col, _prev_row, _prev_col: rvm.select_row(row)
        )

        self.tableRecipes.cellDoubleClicked.connect(
            self._on_recipe_cell_double_clicked
        )

        if rvm.current_index >= 0:
            self.tableRecipes.selectRow(rvm.current_index)

    @pyqtSlot()
    def _apply_selected_recipe(self):
        self.recipe_vm.apply_selected()

        # После выбора рецепта возвращаемся на рабочий экран.
        self.stackedWidget.setCurrentIndex(1)

    @pyqtSlot(list)
    def _on_recipes_changed(self, recipes: list):
        table = self.tableRecipes

        table.blockSignals(True)
        table.setRowCount(0)
        table.setColumnCount(len(RECIPE_HEADERS))
        table.setHorizontalHeaderLabels(list(RECIPE_HEADERS))
        table.verticalHeader().setVisible(True)

        for row, recipe in enumerate(recipes):
            table.insertRow(row)

            # Номер режима назначает сама Qt-таблица через вертикальный заголовок.
            table.setVerticalHeaderItem(row, QtWidgets.QTableWidgetItem(str(row + 1)))

            for col, key in enumerate(RECIPE_COLUMNS):
                table.setItem(row, col, QtWidgets.QTableWidgetItem(str(recipe.get(key, ""))))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.blockSignals(False)

        if 0 <= self.recipe_vm.current_index < table.rowCount():
            table.selectRow(self.recipe_vm.current_index)


    @pyqtSlot(int)
    def _on_recipe_selection_changed(self, index: int):
        if 0 <= index < self.tableRecipes.rowCount():
            self.tableRecipes.selectRow(index)
            self.tableRecipes.scrollToItem(self.tableRecipes.item(index, 0))

    @pyqtSlot(int, int)
    def _on_recipe_cell_double_clicked(self, row: int, col: int):
        item = self.tableRecipes.item(row, col)
        current = item.text() if item else ""

        # Номер режима не редактируется: он находится в вертикальном заголовке Qt.
        if col in RECIPE_NUMERIC_COLUMNS:
            try:
                num = float(current) if current else 0.0
            except ValueError:
                num = 0.0

            dlg = NumericKeyboard(self, num)
            dlg.valueEntered.connect(
                lambda val, r=row, c=col: self.recipe_vm.update_cell(r, c, val)
            )
            dlg.exec()
        else:
            dlg = TextKeyboard(self, current)
            dlg.textEntered.connect(
                lambda text, r=row, c=col: self.recipe_vm.update_cell(r, c, text)
            )
            dlg.exec()

    # ─────────────────────────────────────────────────────────────
    # Отображение рабочих уставок
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(float, float, float, float, float)
    def _on_values_changed(self, propane, oxygen, air, feeder, pistol):
        is_wire = self.vm.current_install == INSTALL_WIRE

        self.lblPropaneWorkWalue.setText(f"{propane:.1f} л/мин")
        self.lblOxygenWorkWalue.setText(f"{oxygen:.1f} л/мин")
        self.lblAirWorkWalue.setText(f"{air:.1f} л/мин")

        if is_wire:
            self.lblQgas_FeederWorkWalue.setText(f"{feeder:.1f} об/мин")
            self.lblQgas_FeederName.setText("Подача")
            self.lblPistol_PatatelWorkWalue.setText(f"{pistol:.1f} об/мин")
            self.lblPistol_PatatelName.setText("Пистолет")
        else:
            self.lblQgas_FeederWorkWalue.setText(f"{feeder:.1f} г/мин")
            self.lblQgas_FeederName.setText("Q газа")
            self.lblPistol_PatatelWorkWalue.setText(f"{pistol:.1f} об/мин")
            self.lblPistol_PatatelName.setText("Пататель")

    # ─────────────────────────────────────────────────────────────
    # Отображение текущих значений от МК / эмулятора
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(float, float, float, float, float)
    def _on_current_values_changed(self, propane, oxygen, air, feeder, pistol):
        is_wire = self.vm.current_install == INSTALL_WIRE

        self.lblPropaneCurrentValue.setText(f"{propane:.1f} л/мин")
        self.lblOxygenCurrentValue.setText(f"{oxygen:.1f} л/мин")
        self.lblAirCurrentValue.setText(f"{air:.1f} л/мин")

        if is_wire:
            self.lblQgas_FeederCurrentWalue.setText(f"{feeder:.1f} об/мин")
            self.lblPistol_PatatelCurrentWalue.setText(f"{pistol:.1f} об/мин")
        else:
            self.lblQgas_FeederCurrentWalue.setText(f"{feeder:.1f} г/мин")
            self.lblPistol_PatatelCurrentWalue.setText(f"{pistol:.1f} об/мин")

    # ─────────────────────────────────────────────────────────────
    # Отображение состояний
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(bool, bool, bool, bool, bool, bool, bool, bool, bool)
    def _on_states_changed(
        self,
        propane_on,
        oxygen_on,
        air_on,
        feeder_on,
        pistol_on,
        system_on,
        ignition_on,
        feeding_on,
        is_wire,
    ):
        checkboxes = [
            self.checkBoxPropaneSwitch,
            self.checkBoxOxygenSwitch,
            self.checkBoxQgas_FeederSwitch,
            self.checkBoxPistol_PatatelSwitch,
            self.checkBoxArcIgnition,
            self.checkBoxFeedingSystem,
        ]

        if hasattr(self, "checkBoxAirSwitch"):
            checkboxes.insert(2, self.checkBoxAirSwitch)

        for checkbox in checkboxes:
            checkbox.blockSignals(True)

        self.checkBoxPropaneSwitch.setChecked(propane_on)
        self.checkBoxOxygenSwitch.setChecked(oxygen_on)

        if hasattr(self, "checkBoxAirSwitch"):
            self.checkBoxAirSwitch.setChecked(air_on)

        self.checkBoxQgas_FeederSwitch.setChecked(feeder_on)
        self.checkBoxPistol_PatatelSwitch.setChecked(pistol_on)
        self.checkBoxArcIgnition.setChecked(ignition_on)
        self.checkBoxFeedingSystem.setChecked(feeding_on)

        for checkbox in checkboxes:
            checkbox.blockSignals(False)

        self.btnStart.setEnabled(not system_on)
        self.btnStop.setEnabled(system_on)

        if ignition_on:
            self.label_25.setText("Дуга горит")
            self.label_25.setStyleSheet("color: #22C55E; font-weight: bold;")
            self.frameIgnition.setStyleSheet(
                "QFrame#frameIgnition { "
                "background-color: #1E2939; "
                "border-radius: 15px; "
                "border: 2px solid #22C55E; "
                "}"
            )
        else:
            self.label_25.setText("Дуга не зажжена")
            self.label_25.setStyleSheet("color: #818181; font-weight: normal;")
            self.frameIgnition.setStyleSheet(
                "QFrame#frameIgnition { "
                "background-color: #1E2939; "
                "border-radius: 15px; "
                "border: 1px solid #364153; "
                "}"
            )

        feeder_label = "Подача проволоки" if is_wire else "Подача порошка"

        if feeding_on:
            self.label.setText(f"{feeder_label}: активна")
            self.label.setStyleSheet("color: #22C55E; font-weight: bold;")
            self.frameFeeding.setStyleSheet(
                "QFrame#frameFeeding { "
                "border-radius: 15px; "
                "border: 2px solid #22C55E; "
                "}"
            )
        else:
            self.label.setText(f"{feeder_label}: остановлена")
            self.label.setStyleSheet("color: #818181; font-weight: normal;")
            self.frameFeeding.setStyleSheet(
                "QFrame#frameFeeding { "
                "border-radius: 15px; "
                "border: 1px solid #364153; "
                "}"
            )

        if system_on:
            self.lblSystemStatus.setText("Система работает")
            self.lblSystemStatus.setStyleSheet("color: #22C55E;")
        else:
            self.lblSystemStatus.setText("Система готова")
            self.lblSystemStatus.setStyleSheet("color: #FFFFFF;")

    # ─────────────────────────────────────────────────────────────
    # Заголовок выбранной установки
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_mode_label(self, text: str):
        if hasattr(self, "lblCurrentMainMode"):
            self.lblCurrentMainMode.setText(text)

    @pyqtSlot(str)
    def _on_mode_switch_blocked(self, message: str):
        QtWidgets.QMessageBox.warning(
            self,
            "Переключение режима запрещено",
            message,
        )

    def _open_startup_params_dialog(self):
        """
        Открывает отдельный диалог параметров запуска.
        Вся логика отображения вынесена в views/startup_params_dialog.py.
        """
        self.startup_vm.set_installation(self.vm.current_install)

        dlg = StartupParamsDialog(self.startup_vm, self)
        dlg.exec()

    @pyqtSlot(str, bool, str)
    def _on_error_state_changed(self, install_type: str, has_error: bool, message: str):
        if install_type != self.vm.current_install:
            return

        if has_error:
            self.ledSystemStatus.setProperty("status", "error")
            self.ledSystemStatus.setStyleSheet(
                "QLabel#ledSystemStatus { background-color: #EF4444; border-radius: 15px; }"
            )
            self.lblSystemStatus.setText(message or "Ошибка установки")
            self.lblSystemStatus.setStyleSheet("color: #EF4444;")
        else:
            self.ledSystemStatus.setProperty("status", "ok")
            self.ledSystemStatus.setStyleSheet(
                "QLabel#ledSystemStatus { background-color: #22C55E; border-radius: 15px; }"
            )

    @pyqtSlot(str, bool)
    def _on_link_state_changed(self, install_type: str, connected: bool):
        if install_type != self.vm.current_install:
            return

        if not connected:
            self.ledSystemStatus.setStyleSheet(
                "QLabel#ledSystemStatus { background-color: #EF4444; border-radius: 15px; }"
            )
            self.lblSystemStatus.setText("Нет связи с МК")
            self.lblSystemStatus.setStyleSheet("color: #EF4444;")

    def request_close(self):
        self.close()

    def closeEvent(self, event):
        if self.vm.is_any_system_active():
            QtWidgets.QMessageBox.warning(
                self,
                "Выход запрещён",
                "Нельзя закрыть приложение, пока активна система.\n\n"
                "Сначала остановите систему, выключите зажигание, подачу "
                "и все активные узлы.",
            )
            event.ignore()
            return

        result = QtWidgets.QMessageBox.question(
            self,
            "Подтверждение выхода",
            "Закрыть приложение?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )

        if result == QtWidgets.QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()