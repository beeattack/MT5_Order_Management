from __future__ import annotations

import psutil

_MT5_IMPORT_ERROR = ""
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except Exception as e:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False
    _MT5_IMPORT_ERROR = f"{type(e).__name__}: {e}"


_MT5_PROCESS_NAMES = {"terminal64.exe", "terminal.exe"}


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

        ok = mt5.initialize()
        if ok:
            self._connected = True
            return True, ""

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

    def get_account_info(self) -> dict | None:
        if not MT5_AVAILABLE or not self.is_connected():
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return info._asdict()
