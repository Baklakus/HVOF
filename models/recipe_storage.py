"""
models/recipe_storage.py

Хранилище рабочих режимов / рецептов HMI HVoF.
Номер режима не хранится в JSON: его показывает QTableWidget через вертикальный заголовок.
"""

import json
import os

from utils.constants import (
    RECIPES_FILE,
    INSTALL_WIRE,
    INSTALL_TYPES,
    DEFAULT_RECIPES,
    RECIPE_COLUMNS,
)


class RecipeStorage:
    def __init__(self, filepath: str = RECIPES_FILE):
        self.filepath = filepath
        self.recipes: dict[str, list[dict]] = {}
        self.load()

    @staticmethod
    def _copy_defaults() -> dict[str, list[dict]]:
        return {
            install: [recipe.copy() for recipe in recipes]
            for install, recipes in DEFAULT_RECIPES.items()
        }

    @staticmethod
    def _string_value(recipe: dict, *keys: str, default: str = "") -> str:
        for key in keys:
            value = recipe.get(key)
            if value not in (None, ""):
                return str(value)
        return default

    @staticmethod
    def _float_value(recipe: dict, *keys: str, default: float = 0.0) -> float:
        for key in keys:
            value = recipe.get(key)
            if value not in (None, ""):
                return float(value)
        return float(default)

    @classmethod
    def _normalize_recipe(cls, recipe: dict, index: int) -> dict:
        """
        Поддерживает старый формат:
            name, propane, oxygen, feeder_speed

        И новый формат ТЗ:
            material, diameter, gas_ratio, propane, oxygen, air,
            feeder_speed, pistol_speed
        """
        material = cls._string_value(
            recipe,
            "material",
            "name",
            default=f"Режим {index}",
        )

        propane = cls._float_value(recipe, "propane")
        oxygen = cls._float_value(recipe, "oxygen")
        air = cls._float_value(recipe, "air")

        return {
            "material": material,
            "diameter": cls._float_value(recipe, "diameter"),
            "gas_ratio": cls._string_value(
                recipe,
                "gas_ratio",
                default=f"{propane:g}/{oxygen:g}/{air:g}",
            ),
            "propane": propane,
            "oxygen": oxygen,
            "air": air,
            "feeder_speed": cls._float_value(recipe, "feeder_speed", "feeder"),
            "pistol_speed": cls._float_value(recipe, "pistol_speed", "pistol"),
        }

    def _normalize_storage(self, data) -> dict[str, list[dict]]:
        defaults = self._copy_defaults()

        if isinstance(data, dict):
            normalized = defaults

            for install in INSTALL_TYPES:
                rows = data.get(install)

                if isinstance(rows, list):
                    normalized[install] = [
                        self._normalize_recipe(recipe, i + 1)
                        for i, recipe in enumerate(rows)
                        if isinstance(recipe, dict)
                    ]

            return normalized

        return defaults

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as file:
                    self.recipes = self._normalize_storage(json.load(file))
            except (json.JSONDecodeError, IOError, TypeError, ValueError):
                self.recipes = self._copy_defaults()
        else:
            self.recipes = self._copy_defaults()

        self.save()

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(self.recipes, file, ensure_ascii=False, indent=2)

    def get_recipes(self, install: str) -> list[dict]:
        if install not in INSTALL_TYPES:
            install = INSTALL_WIRE

        return self.recipes.setdefault(
            install,
            [recipe.copy() for recipe in DEFAULT_RECIPES[install]],
        )

    def update_recipe(self, install: str, index: int, col: int, value):
        rows = self.get_recipes(install)

        if not (0 <= index < len(rows)):
            return

        if not (0 <= col < len(RECIPE_COLUMNS)):
            return

        key = RECIPE_COLUMNS[col]

        if key in ("diameter", "propane", "oxygen", "air", "feeder_speed", "pistol_speed"):
            value = float(value)
        else:
            value = str(value)

        rows[index][key] = value
        self.save()

    def add_recipe(self, install: str):
        rows = self.get_recipes(install)
        next_number = len(rows) + 1
        base = DEFAULT_RECIPES[install][0]

        material_prefix = "Проволока" if install == INSTALL_WIRE else "Порошок"

        new_recipe = {
            "material": f"{material_prefix} {next_number}",
            "diameter": base.get("diameter", 0.0),
            "gas_ratio": base.get("gas_ratio", ""),
            "propane": base.get("propane", 0.0),
            "oxygen": base.get("oxygen", 0.0),
            "air": base.get("air", 0.0),
            "feeder_speed": base.get("feeder_speed", 0.0),
            "pistol_speed": base.get("pistol_speed", 0.0),
        }

        rows.append(new_recipe)
        self.save()
        return len(rows) - 1

    def reset_to_defaults(self):
        self.recipes = self._copy_defaults()
        self.save()
