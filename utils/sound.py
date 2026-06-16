"""Simple non-blocking alert sound for Windows.

Uses the stdlib `winsound` (always present on Windows, nothing to bundle and
no QtMultimedia dependency). MessageBeep returns immediately, so it won't
block the UI thread. No-ops gracefully where winsound is unavailable.
"""
from __future__ import annotations

try:
    import winsound
    _AVAILABLE = True
except ImportError:
    winsound = None  # type: ignore[assignment]
    _AVAILABLE = False


def play_alert() -> None:
    if not _AVAILABLE:
        return
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass
