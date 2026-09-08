from __future__ import annotations

import psutil

from core import server_clock

_MT5_IMPORT_ERROR = ""
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except Exception as e:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False
    _MT5_IMPORT_ERROR = f"{type(e).__name__}: {e}"


_MT5_PROCESS_NAMES = {"terminal64.exe", "terminal.exe"}

# How long (ms) to wait for the terminal during initialize(). The library
# default is 60 s, which freezes the GUI thread while the terminal is busy
# (e.g. mid broker-account switch). A short timeout fails fast instead.
_INIT_TIMEOUT_MS = 10000


class MT5Connector:
    def __init__(self) -> None:
        self._connected: bool = False

    def detect(self) -> bool:
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in _MT5_PROCESS_NAMES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def connect(self) -> tuple[bool, str]:
        if not MT5_AVAILABLE:
            return False, f"MetaTrader5 import failed: {_MT5_IMPORT_ERROR}"

        # Drop any stale session first. After switching broker accounts in the
        # terminal, a previously-initialized handle still points at the old
        # account and can make initialize() block; shutting down forces a clean
        # re-attach to whatever account the terminal is now on.
        try:
            mt5.shutdown()
        except Exception:
            pass

        ok = mt5.initialize(timeout=_INIT_TIMEOUT_MS)
        if ok:
            self._connected = True
            server_clock.reset()
            server_clock.calibrate()
            return True, ""

        self._connected = False
        code, description = mt5.last_error()
        return False, f"[{code}] {description}"

    def disconnect(self) -> None:
        if MT5_AVAILABLE:
            mt5.shutdown()
        self._connected = False

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE or not self._connected:
            return False
        return mt5.terminal_info() is not None

    def copy_rates(self, symbol: str, tf_name: str, count: int):
        """Recent bars for *symbol* on the named timeframe ("M15", "H1", ...).

        Returns the raw MT5 structured array (time/open/high/low/close/...) or
        None. Like every other MT5 call here it runs on the main thread.
        """
        if not MT5_AVAILABLE or not self.is_connected() or not symbol:
            return None
        tf = getattr(mt5, f"TIMEFRAME_{tf_name}", None)
        if tf is None:
            return None
        try:
            mt5.symbol_select(symbol, True)
            return mt5.copy_rates_from_pos(symbol, tf, 0, count)
        except Exception:
            return None

    def symbol_digits(self, symbol: str, default: int = 5) -> int:
        """Price decimals for *symbol* — 5 for most FX, 3 for JPY, 2 for metals."""
        if not MT5_AVAILABLE or not self.is_connected() or not symbol:
            return default
        try:
            info = mt5.symbol_info(symbol)
        except Exception:
            info = None
        return int(getattr(info, "digits", default)) if info else default

    def get_account_info(self) -> dict | None:
        if not MT5_AVAILABLE or not self.is_connected():
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return info._asdict()
