"""Shared constants and helpers for distinguishing auto-trade orders from
manual ones. Kept dependency-free so both the core managers and the UI panels
can import it without cycles.
"""
from __future__ import annotations

# Magic number stamped on every position the auto-trader opens, so it (and the
# UI) can tell its own trades apart from positions opened manually in MT5.
AUTO_TRADE_MAGIC = 778899

AUTO_ICON = "\U0001F916"    # 🤖 robot
MANUAL_ICON = "\U0001F464"  # 👤 bust


def is_auto_magic(magic: int) -> bool:
    return magic == AUTO_TRADE_MAGIC


def source_icon(is_auto: bool) -> str:
    return AUTO_ICON if is_auto else MANUAL_ICON


def source_label(is_auto: bool) -> str:
    return "Auto-trade order" if is_auto else "Manual order"
