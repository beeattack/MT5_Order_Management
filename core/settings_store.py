"""Small persistent key/value store for app settings (timezone, auto-trade
config, ghost-mode geometry, …).

Backed by a single JSON file in the user profile — the same convention used by
`core/watchlist.py`. All access is dict-like; every `set`/`update` writes the
file immediately so values survive an unexpected exit. Missing/corrupt files
degrade silently to defaults.
"""
from __future__ import annotations

import json
import os

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".mt5_order_manager")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "settings.json")


class SettingsStore:
    def __init__(self) -> None:
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    def update(self, mapping: dict) -> None:
        self._data.update(mapping)
        self.save()

    def save(self) -> None:
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass
