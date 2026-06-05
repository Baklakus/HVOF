"""
models/startup_params_storage.py

Хранилище параметров запуска установки.

Отвечает только за:
- загрузку startup_params.json;
- сохранение startup_params.json;
- хранение отдельных параметров запуска для ПРОВОЛОКИ и ПОРОШКА.
"""

import json
import os

from utils.constants import (
    INSTALL_WIRE,
    INSTALL_TYPES,
    DEFAULT_STARTUP_PARAMS,
    STARTUP_PARAMS_FILE,
)


class StartupParamsStorage:
    def __init__(self, filepath: str = STARTUP_PARAMS_FILE):
        self.filepath = filepath
        self.params: dict[str, dict] = {}
        self.load()

    @staticmethod
    def _copy_defaults() -> dict[str, dict]:
        return {
            install: values.copy()
            for install, values in DEFAULT_STARTUP_PARAMS.items()
        }

    @staticmethod
    def _normalize_params(values: dict, defaults: dict) -> dict:
        result = defaults.copy()

        if not isinstance(values, dict):
            return result

        for key in result:
            try:
                result[key] = float(values.get(key, result[key]))
            except (TypeError, ValueError):
                pass

        return result

    def _normalize_storage(self, data) -> dict[str, dict]:
        defaults = self._copy_defaults()

        if not isinstance(data, dict):
            return defaults

        normalized = defaults

        for install in INSTALL_TYPES:
            normalized[install] = self._normalize_params(
                data.get(install, {}),
                defaults[install],
            )

        return normalized

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as file:
                    self.params = self._normalize_storage(json.load(file))
            except (json.JSONDecodeError, IOError, TypeError, ValueError):
                self.params = self._copy_defaults()
        else:
            self.params = self._copy_defaults()

        self.save()

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(self.params, file, ensure_ascii=False, indent=2)

    def get_params(self, install: str) -> dict:
        if install not in INSTALL_TYPES:
            install = INSTALL_WIRE

        return self.params.setdefault(
            install,
            DEFAULT_STARTUP_PARAMS[install].copy(),
        )

    def update_param(self, install: str, key: str, value):
        rows = self.get_params(install)

        if key not in rows:
            return

        try:
            rows[key] = float(value)
        except (TypeError, ValueError):
            return

        self.save()

    def reset_to_defaults(self, install: str | None = None):
        if install is None:
            self.params = self._copy_defaults()
        elif install in INSTALL_TYPES:
            self.params[install] = DEFAULT_STARTUP_PARAMS[install].copy()

        self.save()