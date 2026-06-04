"""
viewmodels/main_view_model.py

ViewModel главного рабочего экрана HMI HVoF.

Этот класс отвечает за:
- выбранную установку: проволока / порошок;
- отображаемые уставки рабочего экрана;
- текущие значения, приходящие от МК / эмулятора;
- состояния кнопок и чекбоксов;
- применение рецепта;
- отправку сигналов на DataManager.

UI-кода здесь быть не должно.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_POWDER,
    INSTALL_TYPES,
    INSTALL_TITLES,
    DEFAULT_SETPOINTS,
    DEFAULT_CURRENT_VALUES,
    SETPOINT_STEPS,
    DEFAULT_NODE_STATES,
)


class MainViewModel(QObject):
    """
    ViewModel главного экрана.

    Раньше этот класс находился внутри большого main.py.
    Теперь он вынесен в отдельный файл согласно архитектуре:
        viewmodels/main_view_model.py
    """

    # Сигналы в DataManager:
    # установка, параметр, значение
    requestPacketSend = pyqtSignal(str, str, float)

    # установка, команда, состояние
    requestCommandSend = pyqtSignal(str, str, bool)

    # Уставки, которые отображаются как рабочие значения
    valuesChanged = pyqtSignal(float, float, float, float, float)

    # Текущие значения, которые приходят от МК / эмулятора
    currentValuesChanged = pyqtSignal(float, float, float, float, float)

    # Состояния UI:
    # propane_on,
    # oxygen_on,
    # air_on,
    # feeder_on,
    # pistol_on,
    # system_on,
    # ignition_on,
    # feeding_on,
    # is_wire
    statesChanged = pyqtSignal(bool, bool, bool, bool, bool, bool, bool, bool, bool)

    # Индекс страницы stackedWidget
    pageChanged = pyqtSignal(int)

    # Заголовок выбранной установки
    modeLabelChanged = pyqtSignal(str)

    # Смена установки для других ViewModel, например RecipeViewModel
    installationChanged = pyqtSignal(str)

    # Текущий применённый рецепт
    currentRecipeChanged = pyqtSignal(str)
    modeSwitchBlocked = pyqtSignal(str)


    def __init__(self):
        super().__init__()

        self.current_install = INSTALL_WIRE

        # Отображаемые рабочие уставки.
        # Пользователь меняет их кнопками + / -.
        self._disp = {
            INSTALL_WIRE: DEFAULT_SETPOINTS[INSTALL_WIRE].copy(),
            INSTALL_POWDER: DEFAULT_SETPOINTS[INSTALL_POWDER].copy(),
        }

        # Активные уставки.
        # Они считаются применёнными после нажатия "SET".
        self._active = {
            INSTALL_WIRE: DEFAULT_SETPOINTS[INSTALL_WIRE].copy(),
            INSTALL_POWDER: DEFAULT_SETPOINTS[INSTALL_POWDER].copy(),
        }

        # Текущие значения от МК / эмулятора.
        self._current = {
            INSTALL_WIRE: DEFAULT_CURRENT_VALUES[INSTALL_WIRE].copy(),
            INSTALL_POWDER: DEFAULT_CURRENT_VALUES[INSTALL_POWDER].copy(),
        }

        self._step = SETPOINT_STEPS.copy()

        # Пока оставляем так же, как было в большом main.py:
        # состояния узлов общие для текущей выбранной установки.
        self.node_states = DEFAULT_NODE_STATES.copy()

        self.system_active = False
        self.ignition_active = False
        self.feeding_active = False

    # ─────────────────────────────────────────────────────────────
    # Внутренние helpers
    # ─────────────────────────────────────────────────────────────

    def _disp_now(self) -> dict:
        return self._disp[self.current_install]

    def _active_now(self) -> dict:
        return self._active[self.current_install]

    def _current_now(self) -> dict:
        return self._current[self.current_install]

    def _emit_current(self):
        """
        Отправляет текущие значения выбранной установки во View.
        """
        c = self._current_now()

        self.currentValuesChanged.emit(
            c["propane"],
            c["oxygen"],
            c["air"],
            c["feeder"],
            c["pistol"],
        )

    def _emit_all(self):
        """
        Обновляет все данные, которые отображает View.
        """
        d = self._disp_now()

        self.valuesChanged.emit(
            d["propane"],
            d["oxygen"],
            d["air"],
            d["feeder"],
            d["pistol"],
        )

        self._emit_current()

        self.statesChanged.emit(
            self.node_states["propane"],
            self.node_states["oxygen"],
            self.node_states["air"],
            self.node_states["feeder"],
            self.node_states["pistol"],
            self.system_active,
            self.ignition_active,
            self.feeding_active,
            self.current_install == INSTALL_WIRE,
        )

    # ─────────────────────────────────────────────────────────────
    # Приём текущих значений от DataManager
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, float)
    def update_current_value(self, install_type: str, param: str, value: float):
        """
        Слот для текущих значений от МК / эмулятора.

        Его подключаем так:

            data_manager.currentValueChanged.connect(
                main_vm.update_current_value
            )
        """
        if install_type not in INSTALL_TYPES:
            return

        if param not in self._current[install_type]:
            return

        self._current[install_type][param] = round(float(value), 2)

        if install_type == self.current_install:
            self._emit_current()

    def is_any_system_active(self) -> bool:
        """
        Проверяет, активна ли хоть одна система.

        Если активно что-то из этого:
        - основная система;
        - зажигание;
        - система подачи;
        - любой узел: пропан, кислород, воздух, подача, пистолет;

        то переключать основной режим wire/powder запрещено.
        """
        return (
                self.system_active
                or self.ignition_active
                or self.feeding_active
                or any(self.node_states.values())
        )




    # ─────────────────────────────────────────────────────────────
    # Выбор установки
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def select_installation(self, install_type: str):
        """
        Выбор установки:
        - wire
        - powder

        Если уже выбран один основной режим и активна хотя бы одна система,
        переход в другой основной режим запрещён.
        """
        if install_type not in INSTALL_TYPES:
            return

        # Если пользователь нажал на уже выбранный режим — просто переходим
        # на рабочий экран и обновляем данные.
        if install_type == self.current_install:
            label = INSTALL_TITLES[install_type]

            self.modeLabelChanged.emit(label)
            self.installationChanged.emit(install_type)
            self.pageChanged.emit(1)
            self._emit_all()
            return

        # Если пытаемся перейти в другой режим при активной системе — запрещаем.
        if self.is_any_system_active():
            self.modeSwitchBlocked.emit(
                "Нельзя переключить основной режим, пока активна система. "
                "Остановите систему, зажигание, подачу и отключите все узлы."
            )
            return

        self.current_install = install_type
        label = INSTALL_TITLES[install_type]

        self.modeLabelChanged.emit(label)
        self.installationChanged.emit(install_type)
        self.currentRecipeChanged.emit("«Текущий режим: не выбран»")

        # 0 — стартовое окно, 1 — рабочий экран
        self.pageChanged.emit(1)

        self._emit_all()


    @pyqtSlot()
    def go_back(self):
        """
        Возврат на стартовую страницу выбора установки.
        """
        self.pageChanged.emit(0)

    # ─────────────────────────────────────────────────────────────
    # Изменение уставок кнопками + / -
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def on_increment(self, param: str):
        d = self._disp_now()

        if param in d:
            d[param] = round(d[param] + self._step[param], 2)
            self._emit_all()

    @pyqtSlot(str)
    def on_decrement(self, param: str):
        d = self._disp_now()

        if param in d and d[param] - self._step[param] >= 0:
            d[param] = round(d[param] - self._step[param], 2)
            self._emit_all()

    @pyqtSlot(str)
    def commit_setpoint(self, param: str):
        """
        Применение уставки.
        После нажатия SET значение отправляется в DataManager.
        """
        d = self._disp_now()
        a = self._active_now()

        if param in d:
            a[param] = d[param]
            self.requestPacketSend.emit(self.current_install, param, a[param])
            self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Команды системы
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(bool)
    def set_main_system_state(self, active: bool):
        """
        Включение / выключение основной системы.
        """
        self.system_active = active

        if not active:
            for key in self.node_states:
                self.node_states[key] = False

            self.ignition_active = False
            self.feeding_active = False

        self.requestCommandSend.emit(self.current_install, "main_system", active)
        self._emit_all()

    @pyqtSlot(str, bool)
    def toggle_node(self, node: str, state: bool):
        """
        Включение / выключение отдельного узла:
        - propane
        - oxygen
        - air
        - feeder
        - pistol
        """
        if node not in self.node_states:
            return

        self.node_states[node] = state

        cmd_map = {
            "propane": "propane_valve",
            "oxygen": "oxygen_valve",
            "air": "air_valve",
            "feeder": "feeder_motor",
            "pistol": "pistol_motor",
        }

        self.requestCommandSend.emit(
            self.current_install,
            cmd_map[node],
            state,
        )

        self._emit_all()

    @pyqtSlot(bool)
    def set_ignition_state(self, state: bool):
        """
        Включение / выключение зажигания дуги.
        """
        self.ignition_active = state

        self.requestCommandSend.emit(
            self.current_install,
            "ignition",
            state,
        )

        self._emit_all()

    @pyqtSlot(bool)
    def set_feeding_state(self, state: bool):
        """
        Включение / выключение системы подачи.
        """
        self.feeding_active = state

        self.requestCommandSend.emit(
            self.current_install,
            "feeding_system",
            state,
        )

        self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Рецепты
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def apply_recipe(self, recipe: dict):
        """
        Применяет выбранный рецепт.

        Сейчас рецепт содержит:
        - propane
        - oxygen
        - feeder_speed

        Эти значения переносятся в рабочие уставки и отправляются в DataManager.
        """
        d = self._disp_now()
        a = self._active_now()

        for param in ("propane", "oxygen"):
            val = recipe.get(param)

            if val is not None:
                d[param] = float(val)
                a[param] = float(val)

                self.requestPacketSend.emit(
                    self.current_install,
                    param,
                    float(val),
                )

        feed = recipe.get("feeder_speed")

        if feed is not None:
            d["feeder"] = float(feed)
            a["feeder"] = float(feed)

            self.requestPacketSend.emit(
                self.current_install,
                "feeder",
                float(feed),
            )

        name = recipe.get("name", "")
        self.currentRecipeChanged.emit(f"«Текущий режим: {name}»")

        self._emit_all()