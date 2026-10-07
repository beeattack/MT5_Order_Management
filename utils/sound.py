"""Alert sounds for Windows.

`play_alert` is the short system beep used by watchlist alerts.

`AlarmSound` plays a user-supplied file for the interval alarm. It goes
through MCI (winmm) rather than QtMultimedia: MCI handles both .wav and .mp3
with the codecs Windows already ships, so the bundle stays as it is — the
PyInstaller spec deliberately excludes QtMultimedia, which would otherwise
pull in a media backend for this one feature.

Everything no-ops gracefully off Windows or when a file cannot be opened,
falling back to the system beep so an alarm is never silent by accident.
"""
from __future__ import annotations

import ctypes
import os

try:
    import winsound
    _BEEP_AVAILABLE = True
except ImportError:
    winsound = None  # type: ignore[assignment]
    _BEEP_AVAILABLE = False

try:
    _winmm = ctypes.windll.winmm
    _kernel32 = ctypes.windll.kernel32
    _MCI_AVAILABLE = True
except Exception:
    _winmm = _kernel32 = None  # type: ignore[assignment]
    _MCI_AVAILABLE = False

SOUND_EXTENSIONS = (".wav", ".mp3")
SOUND_FILTER = "Sound files (*.wav *.mp3)"


def play_alert() -> None:
    """Short system beep — used by the watchlist alerts."""
    if not _BEEP_AVAILABLE:
        return
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def is_supported_sound(path: str) -> bool:
    return bool(path) and path.lower().endswith(SOUND_EXTENSIONS)


def _short_path(path: str) -> str:
    """8.3 form of *path*.

    MCI rejects long filenames outright ("The filename is invalid. Make sure
    the filename is not longer than 8 characters..."), so any real path under
    the user profile has to be shortened before it will open.
    """
    if not _MCI_AVAILABLE:
        return path
    buf = ctypes.create_unicode_buffer(1024)
    if _kernel32.GetShortPathNameW(path, buf, 1022):
        return buf.value
    return path


class AlarmSound:
    """Plays one sound file at a time through MCI, with a beep fallback."""

    _alias_seq = 0

    def __init__(self) -> None:
        self._alias: str | None = None

    # -- internals -----------------------------------------------------

    def _send(self, command: str) -> int:
        if not _MCI_AVAILABLE:
            return -1
        try:
            return _winmm.mciSendStringW(command, None, 0, None)
        except Exception:
            return -1

    def _query(self, command: str) -> str:
        if not _MCI_AVAILABLE:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        try:
            if _winmm.mciSendStringW(command, buf, 254, None) == 0:
                return buf.value
        except Exception:
            pass
        return ""

    # -- API -----------------------------------------------------------

    def play(self, path: str) -> bool:
        """Start *path* from the beginning. Falls back to a beep on failure."""
        self.stop()
        if not (_MCI_AVAILABLE and path and os.path.isfile(path)):
            play_alert()
            return False
        AlarmSound._alias_seq += 1
        alias = f"mt5alarm{AlarmSound._alias_seq}"
        if self._send(f'open "{_short_path(path)}" alias {alias}') != 0:
            play_alert()
            return False
        self._alias = alias
        if self._send(f"play {alias} from 0") != 0:
            self.stop()
            play_alert()
            return False
        return True

    def is_playing(self) -> bool:
        if not self._alias:
            return False
        return self._query(f"status {self._alias} mode") == "playing"

    def stop(self) -> None:
        if not self._alias:
            return
        self._send(f"stop {self._alias}")
        self._send(f"close {self._alias}")
        self._alias = None
