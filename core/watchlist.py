"""Watchlist monitor: track a set of symbols and flag when each enters a
clear trend (a good condition to open a trade) versus a choppy one.

Runs on the main thread, driven by a QTimer tick from MainWindow (MT5 is not
thread-safe). For each symbol it reads recent bars on the configured
timeframe, classifies the trend with `trend_detector`, and fires an alert
callback only when a symbol *transitions* into a clear UP/DOWN trend — so the
alert sounds once per trend onset, not on every poll. The watchlist (symbols,
timeframe, mute) persists to a small JSON file in the user profile.
"""
from __future__ import annotations

import json
import os

from core import trend_detector

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

TIMEFRAMES = ["M1", "M5", "M30", "H1", "H4"]
DEFAULT_TIMEFRAME = "H1"

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".mt5_order_manager")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "watchlist.json")


def _tf_constant(name: str):
    return getattr(mt5, f"TIMEFRAME_{name}", None) if MT5_AVAILABLE else None


def market_watch_symbols() -> list[str]:
    """Names of the symbols currently shown in the MT5 Market Watch."""
    if not MT5_AVAILABLE:
        return []
    try:
        syms = mt5.symbols_get()
    except Exception:
        syms = None
    if not syms:
        return []
    return sorted(s.name for s in syms if getattr(s, "visible", False))


class WatchlistMonitor:
    def __init__(self, connector, update_cb=None, alert_cb=None) -> None:
        self.connector = connector
        self.update_cb = update_cb or (lambda sym, reading: None)
        self.alert_cb = alert_cb or (lambda sym, reading: None)

        self.symbols: list[str] = []
        self.timeframe_name: str = DEFAULT_TIMEFRAME
        self.muted: bool = False
        self.enabled: bool = False
        self.lookback: int = 200

        self._last_state: dict[str, str] = {}
        self.load()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def add(self, symbol: str) -> bool:
        symbol = symbol.strip()
        if not symbol or symbol in self.symbols:
            return False
        self.symbols.append(symbol)
        self.save()
        return True

    def remove(self, symbol: str) -> None:
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            self._last_state.pop(symbol, None)
            self.save()

    def set_timeframe(self, name: str) -> None:
        if name != self.timeframe_name:
            self.timeframe_name = name
            self._last_state.clear()   # re-evaluate from scratch on the new TF
            self.save()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        self.save()

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def on_tick(self) -> None:
        if not self.enabled or not MT5_AVAILABLE:
            return
        if self.connector is None or not self.connector.is_connected():
            return
        tf = _tf_constant(self.timeframe_name)
        if tf is None:
            return

        for sym in list(self.symbols):
            try:
                mt5.symbol_select(sym, True)
                rates = mt5.copy_rates_from_pos(sym, tf, 0, self.lookback)
            except Exception:
                rates = None

            if rates is None or len(rates) < 2:
                reading = trend_detector.TrendReading(
                    trend_detector.UNKNOWN, float("nan"), float("nan"), float("nan")
                )
            else:
                reading = trend_detector.detect(rates[:-1])   # closed bars only

            self.update_cb(sym, reading)

            prev = self._last_state.get(sym)
            if reading.is_clear and reading.state != prev:
                self.alert_cb(sym, reading)
            self._last_state[sym] = reading.state

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.symbols = [str(s) for s in data.get("symbols", [])]
            tf = data.get("timeframe", DEFAULT_TIMEFRAME)
            self.timeframe_name = tf if tf in TIMEFRAMES else DEFAULT_TIMEFRAME
            self.muted = bool(data.get("muted", False))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "symbols": self.symbols,
                    "timeframe": self.timeframe_name,
                    "muted": self.muted,
                }, f, indent=2)
        except OSError:
            pass
