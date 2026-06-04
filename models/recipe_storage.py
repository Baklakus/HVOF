"""
models/recipe_storage.py

Хранилище рецептов HMI HVoF.

Этот файл относится к слою Model.
Он отвечает только за:
- загрузку recipes.json;
- сохранение recipes.json;
- хранение отдельных таблиц рецептов для проволоки и порошка;
- обновление ячеек рецептов;
- добавление новых рецептов.

"""

import json
import os

from utils.constants import (
    RECIPES_FILE,
    INSTALL_WIRE,
    INSTALL_POWDER,
    INSTALL_TYPES,
    DEFAULT_RECIPES,
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
    def _normalize_recipe(recipe: dict, number: int) -> dict:
        return {
            "name": str(recipe.get("name", f"Режим {number}")),
            "propane": float(recipe.get("propane", 0.0)),
            "oxygen": float(recipe.get("oxygen", 0.0)),
            "feeder_speed": float(recipe.get("feeder_speed", 0.0)),
        }

    def _normalize_storage(self, data) -> dict[str, list[dict]]:
        """
        Новый формат recipes.json:

        {
            "wire": [...],
            "powder": [...]
        }

        Старый формат в виде общего списка больше не переносится.
        Если найден старый список, он удаляется и заменяется новыми
        раздельными рецептами для проволоки и порошка.
        """
        defaults = self._copy_defaults()

        if isinstance(data, dict):
            normalized = defaults

            for install in INSTALL_TYPES:
                rows = data.get(install)

                if isinstance(rows, list):
                    normalized[install] = [
                        self._normalize_recipe(recipe, i + 1)
                        for i, recipe in enumerate(rows)
                    ]

            return normalized

        return defaults

    def load(self):
        """
        Загружает рецепты из recipes.json.
        Если файла нет или он повреждён — создаёт таблицы по умолчанию.
        """
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
        """
        Сохраняет рецепты в recipes.json.
        """
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(self.recipes, file, ensure_ascii=False, indent=2)

    def get_recipes(self, install: str) -> list[dict]:
        """
        Возвращает список рецептов для выбранной установки:
        - wire
        - powder
        """
        if install not in INSTALL_TYPES:
            install = INSTALL_WIRE

        return self.recipes.setdefault(
            install,
            [recipe.copy() for recipe in DEFAULT_RECIPES[install]],
        )

    def update_recipe(self, install: str, index: int, col: int, value):
        """
        Обновляет одну ячейку рецепта.

        Теперь в таблице нет колонки number.

        col:
            0 -> name
            1 -> propane
            2 -> oxygen
            3 -> feeder_speed
        """
        rows = self.get_recipes(install)

        col_map = {
            0: "name",
            1: "propane",
            2: "oxygen",
            3: "feeder_speed",
        }

        key = col_map.get(col)

        if key and 0 <= index < len(rows):
            if key in ("propane", "oxygen", "feeder_speed"):
                value = float(value)

            rows[index][key] = value
            self.save()

    def add_recipe(self, install: str):
        """
        Добавляет новый рецепт в таблицу выбранной установки.
        Возвращает индекс добавленной строки.
        """
        rows = self.get_recipes(install)

        next_number = max(
            [int(recipe.get("number", 0)) for recipe in rows],
            default=0,
        ) + 1

        prefix = "Проволока" if install == INSTALL_WIRE else "Порошок"
        base = DEFAULT_RECIPES[install][0]

        new_recipe = {
            "number": next_number,
            "name": f"{prefix} {next_number}",
            "propane": base["propane"],
            "oxygen": base["oxygen"],
            "feeder_speed": base["feeder_speed"],
        }

        rows.append(new_recipe)
        self.save()

        return len(rows) - 1

    def reset_to_defaults(self):
        """
        Полностью сбрасывает рецепты к значениям по умолчанию.
        Может пригодиться для отладки или кнопки сброса.
        """
        self.recipes = self._copy_defaults()
        self.save()