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

# Timeframes shown as columns — each symbol's trend is evaluated on all of them.
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
TIMEFRAME_LABELS = {
    "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
    "H1": "H1", "H4": "H4", "D1": "Day",
}

# Alerts fire only for these timeframes — M1/M5 transition too often and would
# drown the log and the sound. Every timeframe still *displays* its trend.
ALERT_TIMEFRAMES = ("M15", "M30", "H1", "H4", "D1")

# Confluence alert: fires when all of these agree on one clear direction.
CONFLUENCE_TFS = ("M15", "M30", "H1")
CONFLUENCE_LABEL = "M15+M30+H1"

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
        self.update_cb = update_cb or (lambda sym, readings: None)
        self.alert_cb = alert_cb or (lambda sym, tf, reading: None)

        self.symbols: list[str] = []
        self.muted: bool = False
        self.enabled: bool = False
        self.lookback: int = 250   # enough bars for EMA50 on every timeframe

        # (symbol, timeframe) -> last trend state, to alert only on transitions
        self._last_state: dict[tuple[str, str], str] = {}
        # symbol -> last confluence direction ("UP"/"DOWN"/"NONE"), same pattern
        self._last_confluence: dict[str, str] = {}
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
            for key in [k for k in self._last_state if k[0] == symbol]:
                self._last_state.pop(key, None)
            self._last_confluence.pop(symbol, None)
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

        for sym in list(self.symbols):
            try:
                mt5.symbol_select(sym, True)
            except Exception:
                pass

            readings: dict[str, trend_detector.TrendReading] = {}
            for tf_name in TIMEFRAMES:
                reading = self._read(sym, tf_name)
                readings[tf_name] = reading

                # Alert only on a genuine transition into a clear trend. The
                # first evaluation of each (symbol, timeframe) just seeds the
                # baseline silently, so adding a symbol that's already trending
                # on several timeframes doesn't fire a burst of alerts at once.
                key = (sym, tf_name)
                prev = self._last_state.get(key)
                if (prev is not None and reading.is_clear and reading.state != prev
                        and tf_name in ALERT_TIMEFRAMES):
                    self.alert_cb(sym, tf_name, reading)
                self._last_state[key] = reading.state

            self._check_confluence(sym, readings)
            self.update_cb(sym, readings)

    def _check_confluence(self, sym: str, readings: dict) -> None:
        """Fire one alert when CONFLUENCE_TFS first all align in a clear
        direction (transition-based, seeded silently like per-TF alerts)."""
        states = {readings[tf].state for tf in CONFLUENCE_TFS}
        if len(states) == 1 and (s := states.pop()) in (trend_detector.UP, trend_detector.DOWN):
            conf = s
        else:
            conf = "NONE"
        prev = self._last_confluence.get(sym)
        if prev is not None and conf != "NONE" and conf != prev:
            self.alert_cb(sym, CONFLUENCE_LABEL, readings[CONFLUENCE_TFS[-1]])
        self._last_confluence[sym] = conf

    def _read(self, sym: str, tf_name: str) -> trend_detector.TrendReading:
        """Trend reading for one symbol on one timeframe (closed bars only)."""
        nan = float("nan")
        tf = _tf_constant(tf_name)
        if tf is None:
            return trend_detector.TrendReading(trend_detector.UNKNOWN, nan, nan, nan)
        try:
            rates = mt5.copy_rates_from_pos(sym, tf, 0, self.lookback)
        except Exception:
            rates = None
        if rates is None or len(rates) < 2:
            return trend_detector.TrendReading(trend_detector.UNKNOWN, nan, nan, nan)
        # prev_state enables the detector's hysteresis (hold thresholds)
        return trend_detector.detect(
            rates[:-1], prev_state=self._last_state.get((sym, tf_name))
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.symbols = [str(s) for s in data.get("symbols", [])]
            self.muted = bool(data.get("muted", False))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "symbols": self.symbols,
                    "muted": self.muted,
                }, f, indent=2)
        except OSError:
            pass
