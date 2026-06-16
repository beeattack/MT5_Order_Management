"""Bridge that surfaces alerts inside MetaTrader 5 itself.

The MT5 *Python* API cannot raise a native terminal Alert(), so this writes
each alert as a line to a file in MT5's shared "common" folder
(<Common>\\Files\\mt5om_alerts.txt). A companion MQL5 indicator
(mt5_bridge/WatchlistAlertBridge.mq5), attached to any chart in the terminal,
polls that file and calls Alert() for each new line — producing a real MT5
alert popup + sound.

Best-effort and non-blocking: if MT5 isn't connected or the path is
unavailable, write_alert just returns False.
"""
from __future__ import annotations

import os

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

ALERT_FILENAME = "mt5om_alerts.txt"


def alert_file_path() -> str | None:
    """Path to the shared alert file, or None if MT5 isn't reachable."""
    if not MT5_AVAILABLE:
        return None
    info = mt5.terminal_info()
    if info is None:
        return None
    common = getattr(info, "commondata_path", "")
    if not common:
        return None
    return os.path.join(common, "Files", ALERT_FILENAME)


def write_alert(text: str) -> bool:
    """Append one alert line for the MQL bridge to pick up. ASCII/plain text
    only (the indicator reads it as ANSI). Returns True if written."""
    path = alert_file_path()
    if not path:
        return False
    line = text.replace("\r", " ").replace("\n", " ").strip()
    if not line:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    except OSError:
        return False
