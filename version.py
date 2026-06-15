"""Single source of truth for app version and identity.

Imported by the UI (window title, About dialog) and safe to import from the
PyInstaller bundle. Bump __version__ here on each release.
"""

__version__ = "1.0.0"

APP_NAME = "MT5 Order Manager"
AUTHOR = "Pichean"
YEAR = 2026
GITHUB_URL = "https://github.com/beeattack/MT5_Order_Management"
DESCRIPTION = (
    "A lightweight Windows desktop app for monitoring and managing "
    "MetaTrader 5 positions, with a built-in M1/M5 scalping auto-trader "
    "(paper and live modes)."
)
