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

from core import entry_signal, trend_detector

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

# Entry-signal alerts: a signal bar keeps re-evaluating true until the next
# bar closes, so alerts are deduped on the signal bar's open time; the
# cooldown also silences a re-cross within the next few bars.
ENTRY_COOLDOWN_BARS = 5
TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}

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
    def __init__(self, connector, update_cb=None, alert_cb=None,
                 entry_alert_cb=None) -> None:
        self.connector = connector
        self.update_cb = update_cb or (lambda sym, readings, entries: None)
        self.alert_cb = alert_cb or (lambda sym, tf, reading: None)
        self.entry_alert_cb = entry_alert_cb or (lambda sym, tf, entry: None)

        self.symbols: list[str] = []
        self.muted: bool = False
        self.enabled: bool = False
        self.lookback: int = 250   # enough bars for EMA50 on every timeframe

        # (symbol, timeframe) -> last trend state, to alert only on transitions
        self._last_state: dict[tuple[str, str], str] = {}
        # symbol -> last confluence direction ("UP"/"DOWN"/"NONE"), same pattern
        self._last_confluence: dict[str, str] = {}
        # (symbol, timeframe) -> open time of the last alerted entry-signal bar
        self._last_entry_bar: dict[tuple[str, str], float] = {}
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
            for key in [k for k in self._last_entry_bar if k[0] == symbol]:
                self._last_entry_bar.pop(key, None)
            self._last_confluence.pop(symbol, None)
            self.save()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        self.save()

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def can_scan(self) -> bool:
        """Whether a scan could run right now (MT5 present and connected)."""
        return (MT5_AVAILABLE and self.connector is not None
                and self.connector.is_connected())

    def on_tick(self) -> None:
        if self.enabled:
            self._scan(alerts=True)

    def refresh_now(self) -> int:
        """Re-read every symbol on demand, outside the watch timer. Returns the
        number of symbols scanned, or -1 if MT5 isn't connected.

        Alerts only fire when watching is on: a manual refresh with the watch
        stopped is a look at the current state, not a reason to sound. Alert
        baselines are still updated so a later transition is measured against
        what was just displayed — except the entry-signal bar, which is left
        untouched so a live signal still alerts once watching starts."""
        if not self.can_scan():
            return -1
        self._scan(alerts=self.enabled)
        return len(self.symbols)

    def _scan(self, alerts: bool) -> None:
        if not self.can_scan():
            return

        for sym in list(self.symbols):
            try:
                mt5.symbol_select(sym, True)
            except Exception:
                pass

            readings: dict[str, trend_detector.TrendReading] = {}
            entries: dict[str, entry_signal.EntryReading] = {}
            for tf_name in TIMEFRAMES:
                reading, entry, bar_time = self._read(sym, tf_name)
                readings[tf_name] = reading
                entries[tf_name] = entry

                # Alert only on a genuine transition into a clear trend. The
                # first evaluation of each (symbol, timeframe) just seeds the
                # baseline silently, so adding a symbol that's already trending
                # on several timeframes doesn't fire a burst of alerts at once.
                key = (sym, tf_name)
                prev = self._last_state.get(key)
                if (alerts and prev is not None and reading.is_clear
                        and reading.state != prev and tf_name in ALERT_TIMEFRAMES):
                    self.alert_cb(sym, tf_name, reading)
                self._last_state[key] = reading.state

                # Entry alert: no silent seeding (a fresh signal on a newly
                # added symbol is still actionable), but the same signal bar
                # must not re-alert every poll and a re-cross a bar or two
                # later stays quiet (cooldown).
                if alerts and entry.is_signal and tf_name in ALERT_TIMEFRAMES:
                    last = self._last_entry_bar.get(key)
                    min_gap = ENTRY_COOLDOWN_BARS * TF_SECONDS[tf_name]
                    if last is None or bar_time - last >= min_gap:
                        self.entry_alert_cb(sym, tf_name, entry)
                        self._last_entry_bar[key] = bar_time

            self._check_confluence(sym, readings, alerts)
            self.update_cb(sym, readings, entries)

    def _check_confluence(self, sym: str, readings: dict, alerts: bool = True) -> None:
        """Fire one alert when CONFLUENCE_TFS first all align in a clear
        direction (transition-based, seeded silently like per-TF alerts)."""
        states = {readings[tf].state for tf in CONFLUENCE_TFS}
        if len(states) == 1 and (s := states.pop()) in (trend_detector.UP, trend_detector.DOWN):
            conf = s
        else:
            conf = "NONE"
        prev = self._last_confluence.get(sym)
        if alerts and prev is not None and conf != "NONE" and conf != prev:
            self.alert_cb(sym, CONFLUENCE_LABEL, readings[CONFLUENCE_TFS[-1]])
        self._last_confluence[sym] = conf

    def _read(self, sym: str, tf_name: str):
        """Trend + entry readings for one symbol on one timeframe (closed bars
        only). Returns (TrendReading, EntryReading, signal_bar_open_time)."""
        nan = float("nan")
        no_data = (
            trend_detector.TrendReading(trend_detector.UNKNOWN, nan, nan, nan),
            entry_signal.EntryReading(),
            0.0,
        )
        tf = _tf_constant(tf_name)
        if tf is None:
            return no_data
        try:
            rates = mt5.copy_rates_from_pos(sym, tf, 0, self.lookback)
        except Exception:
            rates = None
        if rates is None or len(rates) < 2:
            return no_data
        closed = rates[:-1]   # drop the still-forming bar
        # prev_state enables the detector's hysteresis (hold thresholds)
        trend = trend_detector.detect(
            closed, prev_state=self._last_state.get((sym, tf_name))
        )
        entry = entry_signal.detect_entry(closed)
        return trend, entry, float(closed[-1]["time"])

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
