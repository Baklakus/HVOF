"""
viewmodels/main_view_model.py

ViewModel главного рабочего экрана HMI HVoF.

Отвечает за:
- выбранную установку: ПРОВОЛОКА / ПОРОШОК;
- отображаемые рабочие уставки;
- текущие значения от МК / эмулятора;
- состояния системы и узлов;
- применение рецептов;
- параметры запуска;
- автоматическую последовательность START;
- безопасную остановку STOP.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_TYPES,
    INSTALL_TITLES,
    DEFAULT_SETPOINTS,
    DEFAULT_CURRENT_VALUES,
    SETPOINT_STEPS,
    DEFAULT_NODE_STATES,
    PARAM_NAMES,
    DEFAULT_STARTUP_PARAMS,
)


class MainViewModel(QObject):
    # ─────────────────────────────────────────────────────────────
    # Сигналы ViewModel -> DataManager
    # ─────────────────────────────────────────────────────────────

    # install, param, value
    requestPacketSend = pyqtSignal(str, str, float)

    # install, command, state
    requestCommandSend = pyqtSignal(str, str, bool)

    # ─────────────────────────────────────────────────────────────
    # Сигналы ViewModel -> View
    # ─────────────────────────────────────────────────────────────

    # propane, oxygen, air, feeder, pistol
    valuesChanged = pyqtSignal(float, float, float, float, float)

    # propane, oxygen, air, feeder, pistol
    currentValuesChanged = pyqtSignal(float, float, float, float, float)

    # propane, oxygen, air, feeder, pistol, system, ignition, feeding, is_wire
    statesChanged = pyqtSignal(bool, bool, bool, bool, bool, bool, bool, bool, bool)

    pageChanged = pyqtSignal(int)
    modeLabelChanged = pyqtSignal(str)
    installationChanged = pyqtSignal(str)
    currentRecipeChanged = pyqtSignal(str)
    modeSwitchBlocked = pyqtSignal(str)

    # install, has_error, message
    errorStateChanged = pyqtSignal(str, bool, str)

    # install, connected
    linkStateChanged = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()

        self.current_install = INSTALL_WIRE

        # Отображаемые рабочие уставки.
        # Это то, что пользователь видит на экране.
        self._disp = {
            install: DEFAULT_SETPOINTS[install].copy()
            for install in INSTALL_TYPES
        }

        # Активные уставки.
        # Это то, что было отправлено в МК.
        self._active = {
            install: DEFAULT_SETPOINTS[install].copy()
            for install in INSTALL_TYPES
        }

        # Текущие значения от МК / эмулятора.
        self._current = {
            install: DEFAULT_CURRENT_VALUES[install].copy()
            for install in INSTALL_TYPES
        }

        self._step = SETPOINT_STEPS.copy()

        # Состояния отдельно для каждой установки.
        self._states = {
            install: {
                "nodes": DEFAULT_NODE_STATES.copy(),
                "system": False,
                "ignition": False,
                "feeding": False,
                "error": False,
                "error_message": "",
                "link_ok": False,
                "startup_in_progress": False,
            }
            for install in INSTALL_TYPES
        }

        # Параметры запуска отдельно для каждой установки.
        # Обновляются из StartupParamsViewModel через set_startup_params().
        self._startup_params = {
            install: DEFAULT_STARTUP_PARAMS[install].copy()
            for install in INSTALL_TYPES
        }

        self._startup_feeding_delay_ms = 0

        self._startup_ignition_timer = QTimer(self)
        self._startup_ignition_timer.setSingleShot(True)
        self._startup_ignition_timer.timeout.connect(self._enable_ignition_stage)

        self._startup_feeding_timer = QTimer(self)
        self._startup_feeding_timer.setSingleShot(True)
        self._startup_feeding_timer.timeout.connect(self._enable_feeding_stage)

        self._startup_working_timer = QTimer(self)
        self._startup_working_timer.setSingleShot(True)
        self._startup_working_timer.timeout.connect(self._switch_to_working_setpoints)

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _disp_now(self) -> dict:
        return self._disp[self.current_install]

    def _active_now(self) -> dict:
        return self._active[self.current_install]

    def _current_now(self) -> dict:
        return self._current[self.current_install]

    def _state_now(self) -> dict:
        return self._states[self.current_install]

    def _emit_current(self):
        current = self._current_now()

        self.currentValuesChanged.emit(
            current["propane"],
            current["oxygen"],
            current["air"],
            current["feeder"],
            current["pistol"],
        )

    def _emit_all(self):
        values = self._disp_now()
        state = self._state_now()
        nodes = state["nodes"]

        self.valuesChanged.emit(
            values["propane"],
            values["oxygen"],
            values["air"],
            values["feeder"],
            values["pistol"],
        )

        self._emit_current()

        self.statesChanged.emit(
            nodes["propane"],
            nodes["oxygen"],
            nodes["air"],
            nodes["feeder"],
            nodes["pistol"],
            state["system"],
            state["ignition"],
            state["feeding"],
            self.current_install == INSTALL_WIRE,
        )

        self.errorStateChanged.emit(
            self.current_install,
            bool(state["error"]),
            str(state["error_message"]),
        )

        self.linkStateChanged.emit(
            self.current_install,
            bool(state["link_ok"]),
        )

    def is_any_system_active(self) -> bool:
        for state in self._states.values():
            if (
                state["system"]
                or state["ignition"]
                or state["feeding"]
                or any(state["nodes"].values())
                or state.get("startup_in_progress", False)
            ):
                return True

        return False

    # ─────────────────────────────────────────────────────────────
    # DataManager -> ViewModel
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, float)
    def update_current_value(self, install_type: str, param: str, value: float):
        if install_type not in INSTALL_TYPES:
            return

        if param not in self._current[install_type]:
            return

        self._current[install_type][param] = round(float(value), 2)
        self._states[install_type]["link_ok"] = True

        if install_type == self.current_install:
            self._emit_current()
            self.linkStateChanged.emit(install_type, True)

    @pyqtSlot(str, bool, str)
    def update_error_state(self, install_type: str, has_error: bool, message: str = ""):
        if install_type not in INSTALL_TYPES:
            return

        state = self._states[install_type]
        state["error"] = bool(has_error)
        state["error_message"] = str(message or "")

        if install_type == self.current_install:
            self.errorStateChanged.emit(
                install_type,
                state["error"],
                state["error_message"],
            )

    @pyqtSlot(str, bool)
    def update_link_state(self, install_type: str, connected: bool):
        if install_type not in INSTALL_TYPES:
            return

        self._states[install_type]["link_ok"] = bool(connected)

        if install_type == self.current_install:
            self.linkStateChanged.emit(install_type, bool(connected))

    # ─────────────────────────────────────────────────────────────
    # Выбор установки
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def select_installation(self, install_type: str):
        if install_type not in INSTALL_TYPES:
            return

        if install_type != self.current_install and self.is_any_system_active():
            self.modeSwitchBlocked.emit(
                "Нельзя переключить основной режим, пока активна система. "
                "Остановите систему, зажигание, подачу и отключите все узлы."
            )
            return

        self.current_install = install_type

        self.modeLabelChanged.emit(INSTALL_TITLES[install_type])
        self.installationChanged.emit(install_type)
        self.currentRecipeChanged.emit("«Текущий режим: не выбран»")
        self.pageChanged.emit(1)

        self._emit_all()

    @pyqtSlot()
    def go_back(self):
        if self.is_any_system_active():
            self.modeSwitchBlocked.emit(
                "Нельзя вернуться к выбору установки, пока активна система. "
                "Сначала остановите установку и отключите узлы."
            )
            return

        self.pageChanged.emit(0)

    # ─────────────────────────────────────────────────────────────
    # Ручное изменение уставок
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def on_increment(self, param: str):
        values = self._disp_now()

        if param not in values:
            return

        values[param] = round(values[param] + self._step[param], 2)
        self._emit_all()

    @pyqtSlot(str)
    def on_decrement(self, param: str):
        values = self._disp_now()

        if param not in values:
            return

        new_value = values[param] - self._step[param]

        if new_value < 0:
            new_value = 0.0

        values[param] = round(new_value, 2)
        self._emit_all()

    @pyqtSlot(str, float)
    def set_display_value(self, param: str, value: float):
        values = self._disp_now()

        if param not in values:
            return

        values[param] = round(max(0.0, float(value)), 2)
        self._emit_all()

    @pyqtSlot(str)
    def commit_setpoint(self, param: str):
        values = self._disp_now()
        active = self._active_now()

        if param not in values:
            return

        active[param] = values[param]

        self.requestPacketSend.emit(
            self.current_install,
            param,
            float(active[param]),
        )

        self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Параметры запуска / автоматический START
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def set_startup_params(self, params: dict):
        """
        Получает актуальные параметры запуска из StartupParamsViewModel.

        Важно:
        StartupParamsViewModel переключается на ту же установку через
        main_vm.installationChanged.connect(startup_vm.set_installation).
        """
        normalized = {}

        for key in (
            "propane",
            "oxygen",
            "air",
            "feeder",
            "pistol",
            "ignition_delay",
            "feeding_delay",
        ):
            try:
                normalized[key] = float(params.get(key, 0.0))
            except (TypeError, ValueError):
                normalized[key] = 0.0

        self._startup_params[self.current_install] = normalized

    def _cancel_startup_sequence(self):
        self._startup_ignition_timer.stop()
        self._startup_feeding_timer.stop()
        self._startup_working_timer.stop()

        self._state_now()["startup_in_progress"] = False

    def _command_for_node(self, node: str) -> str | None:
        cmd_map = {
            "propane": "propane_valve",
            "oxygen": "oxygen_valve",
            "air": "air_valve",
            "feeder": "feeder_motor",
            "pistol": "pistol_motor",
        }

        return cmd_map.get(node)

    def _set_node_state_silent(self, node: str, enabled: bool):
        state = self._state_now()

        if node not in state["nodes"]:
            return

        command = self._command_for_node(node)

        if command is None:
            return

        state["nodes"][node] = bool(enabled)

        self.requestCommandSend.emit(
            self.current_install,
            command,
            bool(enabled),
        )

    @pyqtSlot()
    def start_system_sequence(self):
        """
        Автоматический запуск установки.

        Последовательность:
        1. Отправить пусковые уставки.
        2. Включить main_system.
        3. Открыть газовые клапаны: propane, oxygen, air.
        4. Через ignition_delay включить ignition.
        5. Через feeding_delay включить feeding_system.
        6. Включить feeder / pistol, если их пусковые значения > 0.
        7. Через 0.5 сек перейти на рабочие уставки.
        """
        state = self._state_now()

        if state["system"]:
            return

        if state["error"]:
            self.modeSwitchBlocked.emit(
                "Нельзя запустить установку: активна ошибка.\n"
                "Сначала сбросьте ошибку и проверьте состояние МК."
            )
            return

        self._cancel_startup_sequence()

        params = self._startup_params.get(
            self.current_install,
            DEFAULT_STARTUP_PARAMS[self.current_install],
        )

        state["startup_in_progress"] = True

        # 1. Отправляем пусковые уставки.
        for param in PARAM_NAMES:
            value = float(params.get(param, 0.0))
            self._active_now()[param] = value

            self.requestPacketSend.emit(
                self.current_install,
                param,
                value,
            )

        # 2. Включаем основную систему.
        state["system"] = True

        self.requestCommandSend.emit(
            self.current_install,
            "main_system",
            True,
        )

        # 3. Открываем газовые узлы.
        self._set_node_state_silent("propane", True)
        self._set_node_state_silent("oxygen", True)
        self._set_node_state_silent("air", True)

        ignition_delay_ms = int(
            max(0.0, float(params.get("ignition_delay", 0.0))) * 1000
        )

        self._startup_feeding_delay_ms = int(
            max(0.0, float(params.get("feeding_delay", 0.0))) * 1000
        )

        self._startup_ignition_timer.start(ignition_delay_ms)

        self._emit_all()

    def _enable_ignition_stage(self):
        state = self._state_now()

        if not state["system"]:
            return

        state["ignition"] = True

        self.requestCommandSend.emit(
            self.current_install,
            "ignition",
            True,
        )

        self._startup_feeding_timer.start(self._startup_feeding_delay_ms)

        self._emit_all()

    def _enable_feeding_stage(self):
        state = self._state_now()

        if not state["system"]:
            return

        params = self._startup_params.get(
            self.current_install,
            DEFAULT_STARTUP_PARAMS[self.current_install],
        )

        state["feeding"] = True

        self.requestCommandSend.emit(
            self.current_install,
            "feeding_system",
            True,
        )

        if float(params.get("feeder", 0.0)) > 0.0:
            self._set_node_state_silent("feeder", True)

        if float(params.get("pistol", 0.0)) > 0.0:
            self._set_node_state_silent("pistol", True)

        self._startup_working_timer.start(500)

        self._emit_all()

    def _switch_to_working_setpoints(self):
        state = self._state_now()

        if not state["system"]:
            return

        values = self._disp_now()
        active = self._active_now()

        for param in PARAM_NAMES:
            value = float(values[param])
            active[param] = value

            self.requestPacketSend.emit(
                self.current_install,
                param,
                value,
            )

        state["startup_in_progress"] = False

        self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Команды системы
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(bool)
    def set_main_system_state(self, active: bool):
        """
        active=True:
            запускает автоматическую последовательность START.

        active=False:
            останавливает запуск и переводит установку в безопасное состояние.
        """
        if active:
            self.start_system_sequence()
            return

        self._cancel_startup_sequence()
        self.shutdown_safely()

    @pyqtSlot(str, bool)
    def toggle_node(self, node: str, state: bool):
        current_state = self._state_now()

        if current_state.get("startup_in_progress", False):
            self.modeSwitchBlocked.emit(
                "Во время автоматического запуска ручное управление узлами заблокировано."
            )
            self._emit_all()
            return

        if node not in current_state["nodes"]:
            return

        command = self._command_for_node(node)

        if command is None:
            return

        current_state["nodes"][node] = bool(state)

        self.requestCommandSend.emit(
            self.current_install,
            command,
            bool(state),
        )

        self._emit_all()

    @pyqtSlot(bool)
    def set_ignition_state(self, state: bool):
        current_state = self._state_now()

        if current_state.get("startup_in_progress", False):
            self.modeSwitchBlocked.emit(
                "Во время автоматического запуска ручное включение зажигания заблокировано."
            )
            self._emit_all()
            return

        current_state["ignition"] = bool(state)

        self.requestCommandSend.emit(
            self.current_install,
            "ignition",
            bool(state),
        )

        self._emit_all()

    @pyqtSlot(bool)
    def set_feeding_state(self, state: bool):
        current_state = self._state_now()

        if current_state.get("startup_in_progress", False):
            self.modeSwitchBlocked.emit(
                "Во время автоматического запуска ручное включение подачи заблокировано."
            )
            self._emit_all()
            return

        current_state["feeding"] = bool(state)

        self.requestCommandSend.emit(
            self.current_install,
            "feeding_system",
            bool(state),
        )

        self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Рецепты / рабочие режимы
    # ─────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def apply_recipe(self, recipe: dict):
        values = self._disp_now()
        active = self._active_now()

        mapping = {
            "propane": "propane",
            "oxygen": "oxygen",
            "air": "air",
            "feeder_speed": "feeder",
            "pistol_speed": "pistol",
        }

        for recipe_key, param in mapping.items():
            recipe_value = recipe.get(recipe_key)

            if recipe_value is None:
                continue

            value = float(recipe_value)
            values[param] = value
            active[param] = value

            self.requestPacketSend.emit(
                self.current_install,
                param,
                value,
            )

        name = recipe.get("material") or recipe.get("name") or "без названия"
        diameter = recipe.get("diameter")

        if diameter not in (None, "", 0, 0.0):
            name = f"{name} Ø{float(diameter):g}"

        self.currentRecipeChanged.emit(f"«Текущий режим: {name}»")

        self._emit_all()

    # ─────────────────────────────────────────────────────────────
    # Безопасная остановка
    # ─────────────────────────────────────────────────────────────

    def shutdown_safely(self):
        state = self._state_now()

        state["startup_in_progress"] = False

        for node in ("propane", "oxygen", "air", "feeder", "pistol"):
            state["nodes"][node] = False

        state["ignition"] = False
        state["feeding"] = False
        state["system"] = False

        commands = [
            ("ignition", False),
            ("feeding_system", False),
            ("propane_valve", False),
            ("oxygen_valve", False),
            ("air_valve", False),
            ("feeder_motor", False),
            ("pistol_motor", False),
            ("main_system", False),
        ]

        for command, command_state in commands:
            self.requestCommandSend.emit(
                self.current_install,
                command,
                command_state,
            )

        self._emit_all()