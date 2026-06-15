"""Auto-trading orchestrator for the M1/M5 scalping strategy.

Runs on the main thread, driven by a QTimer tick from MainWindow (MT5 is not
thread-safe). Each tick it: manages exits on open positions, then — only when
a new bar has just *closed* — asks the strategy for a signal and, if the
guardrails pass, opens a position.

Two modes:
  - PAPER: trades are simulated in an in-memory book and marked against live
    bid/ask (so spread cost is real). Nothing is sent to the broker. This is
    the default and the only safe way to evaluate the strategy.
  - LIVE: orders are sent via OrderManager, tagged with AUTO_TRADE_MAGIC so
    the bot only ever manages its own positions.

Daily loss/profit limits, max concurrent positions, a spread gate, a trading
session window, and a hard kill switch all gate entries.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from core import server_clock
from core.risk_manager import RiskManager
from core.strategy import EmaRsiPullbackStrategy
from models.signal import PaperPosition, Signal

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

# Tag for the bot's own positions so it never touches manually-opened trades
AUTO_TRADE_MAGIC = 778899

_TF_SECONDS = {"M1": 60, "M5": 300}
_DEFAULT_BALANCE = 10_000.0


def _tf_constant(name: str):
    return getattr(mt5, f"TIMEFRAME_{name}", None) if MT5_AVAILABLE else None


class PaperBook:
    """In-memory simulated positions for paper mode."""

    def __init__(self) -> None:
        self._positions: list[PaperPosition] = []

    def open(self, pos: PaperPosition) -> None:
        self._positions.append(pos)

    def open_positions(self) -> list[PaperPosition]:
        return list(self._positions)

    def count(self) -> int:
        return len(self._positions)

    def close(self, pos: PaperPosition, exit_price: float, tick_size: float, tick_value: float) -> float:
        sign = 1.0 if pos.direction == "BUY" else -1.0
        diff = (exit_price - pos.entry_price) * sign
        pnl = 0.0
        if tick_size > 0:
            pnl = diff / tick_size * tick_value * pos.volume
        if pos in self._positions:
            self._positions.remove(pos)
        return pnl


class AutoTrader:
    def __init__(self, order_mgr, connector, log_cb=None, stats_cb=None) -> None:
        self.order_mgr = order_mgr
        self.connector = connector
        self.log_cb = log_cb or (lambda msg: None)
        self.stats_cb = stats_cb or (lambda stats: None)

        self.running = False
        self.killed = False
        self.mode = "PAPER"

        self.symbol = ""
        self.timeframe = None
        self._tf_seconds = 300
        self.lookback = 250

        self.strategy = None
        self._risk = RiskManager()

        # config-driven guardrails
        self.time_stop = 12
        self.max_positions = 1
        self.daily_loss_pct = 3.0
        self.daily_profit_pct = 5.0
        self.max_spread_frac = 0.3
        self.session_start = 0
        self.session_end = 24

        self._last_bar_time: int | None = None
        self._paper = PaperBook()
        self._day = None
        self._day_realized = 0.0
        self._day_start_balance = _DEFAULT_BALANCE
        self._trades_today = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, config: dict) -> tuple[bool, str]:
        if not MT5_AVAILABLE:
            return False, "MetaTrader5 package is not available"

        symbol = config["symbol"].strip()
        if not symbol or mt5.symbol_info(symbol) is None:
            return False, f"Unknown symbol '{symbol}'"
        mt5.symbol_select(symbol, True)

        tf_name = config["timeframe"]
        tf = _tf_constant(tf_name)
        if tf is None:
            return False, f"Unsupported timeframe '{tf_name}'"

        self.symbol = symbol
        self.timeframe = tf
        self._tf_seconds = _TF_SECONDS.get(tf_name, 300)
        self.mode = config.get("mode", "PAPER")

        self.time_stop = int(config.get("time_stop", 12))
        self.max_positions = int(config.get("max_positions", 1))
        self.daily_loss_pct = float(config.get("daily_loss_pct", 3.0))
        self.daily_profit_pct = float(config.get("daily_profit_pct", 5.0))
        self.max_spread_frac = float(config.get("max_spread_frac", 0.3))
        self.session_start = int(config.get("session_start", 0))
        self.session_end = int(config.get("session_end", 24))

        self.strategy = EmaRsiPullbackStrategy()
        self._risk = RiskManager(float(config.get("risk_pct", 0.5)))
        self.lookback = max(250, self.strategy.min_bars + 50)

        self.killed = False
        self.running = True
        self._last_bar_time = None
        self._paper = PaperBook()
        self._day = None
        self._day_realized = 0.0
        self._day_start_balance = self._balance()
        self._trades_today = 0

        self.log(
            f"Auto-trade started [{self.mode}] {symbol} {tf_name} | "
            f"risk {self._risk.risk_pct}% | max {self.max_positions} pos"
        )
        self._emit_stats()
        return True, ""

    def stop(self) -> None:
        if self.running:
            self.log("Auto-trade stopped")
        self.running = False
        self._emit_stats()

    def kill(self) -> None:
        self.killed = True
        self.running = False
        self.log("KILL SWITCH — auto-trade halted, no new entries")
        self._emit_stats()

    # ------------------------------------------------------------------
    # Main loop (called from MainWindow's QTimer)
    # ------------------------------------------------------------------

    def on_tick(self) -> None:
        if not self.running or not MT5_AVAILABLE:
            return
        if not self.connector.is_connected():
            self.log("MT5 disconnected — auto-trade paused")
            self.running = False
            self._emit_stats()
            return

        self._roll_day()
        self._manage_exits()

        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, self.lookback)
        if rates is None or len(rates) < self.strategy.min_bars + 1:
            self._emit_stats()
            return

        closed = rates[:-1]              # drop the still-forming bar
        last_closed_time = int(closed[-1]["time"])

        # Prime on the first tick — don't trade a bar that closed before we started
        if self._last_bar_time is None:
            self._last_bar_time = last_closed_time
            self._emit_stats()
            return
        if last_closed_time == self._last_bar_time:
            self._emit_stats()
            return
        self._last_bar_time = last_closed_time

        signal = self.strategy.evaluate(closed)
        if signal is None:
            self._emit_stats()
            return

        ok, reason = self._guardrails(signal)
        if not ok:
            self.log(f"Signal {signal.direction} skipped: {reason}")
            self._emit_stats()
            return

        self._enter(signal)
        self._emit_stats()

    # ------------------------------------------------------------------
    # Entry / exit
    # ------------------------------------------------------------------

    def _enter(self, signal: Signal) -> None:
        info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        if info is None or tick is None:
            self.log("Signal skipped: no market data")
            return

        lots = self._risk.size_lots(self._balance(), info, signal.sl_distance)
        if lots <= 0:
            self.log("Signal skipped: computed lot size is 0 (risk too small for min lot)")
            return

        is_buy = signal.direction == "BUY"
        entry = tick.ask if is_buy else tick.bid
        sl = entry - signal.sl_distance if is_buy else entry + signal.sl_distance
        tp = entry + signal.tp_distance if is_buy else entry - signal.tp_distance
        d = info.digits

        if self.mode == "PAPER":
            self._paper.open(PaperPosition(
                symbol=self.symbol, direction=signal.direction, volume=lots,
                entry_price=entry, sl_price=sl, tp_price=tp,
                open_bar_time=self._last_bar_time or int(tick.time),
            ))
            self.log(
                f"PAPER enter {signal.direction} {lots:g} {self.symbol} @ {entry:.{d}f} "
                f"SL {sl:.{d}f} TP {tp:.{d}f} | {signal.reason}"
            )
        else:
            ok, msg = self.order_mgr.open_order(
                self.symbol, signal.direction, lots,
                signal.sl_distance, signal.tp_distance,
                magic=AUTO_TRADE_MAGIC, comment="auto-scalp",
            )
            self.log(
                f"LIVE enter {signal.direction} {lots:g} {self.symbol}: "
                f"{'OK' if ok else msg} | {signal.reason}"
            )
            if not ok:
                return

        self._trades_today += 1

    def _manage_exits(self) -> None:
        info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        if info is None or tick is None:
            return
        d = info.digits

        if self.mode == "PAPER":
            for pos in self._paper.open_positions():
                close_price = tick.bid if pos.direction == "BUY" else tick.ask
                exit_reason = self._paper_exit_reason(pos, close_price)
                if exit_reason is None:
                    continue
                pnl = self._paper.close(pos, close_price, info.trade_tick_size, info.trade_tick_value)
                self._day_realized += pnl
                self.log(
                    f"PAPER exit {pos.direction} {pos.symbol} @ {close_price:.{d}f} "
                    f"[{exit_reason}] P/L {pnl:+.2f}"
                )
        else:
            positions = [
                p for p in (mt5.positions_get(symbol=self.symbol) or [])
                if p.magic == AUTO_TRADE_MAGIC
            ]
            now_server = time.time() + server_clock.offset_seconds()
            for p in positions:
                if (now_server - p.time) >= self.time_stop * self._tf_seconds:
                    ok, err = self.order_mgr.close_order(p.ticket, p.volume)
                    self.log(f"LIVE time-exit #{p.ticket}: {'closed' if ok else err}")

    def _paper_exit_reason(self, pos: PaperPosition, close_price: float) -> str | None:
        if pos.direction == "BUY":
            if close_price <= pos.sl_price:
                return "SL"
            if close_price >= pos.tp_price:
                return "TP"
        else:
            if close_price >= pos.sl_price:
                return "SL"
            if close_price <= pos.tp_price:
                return "TP"
        if self._last_bar_time is not None:
            bars_held = (self._last_bar_time - pos.open_bar_time) / self._tf_seconds
            if bars_held >= self.time_stop:
                return "TIME"
        return None

    # ------------------------------------------------------------------
    # Guardrails
    # ------------------------------------------------------------------

    def _guardrails(self, signal: Signal) -> tuple[bool, str]:
        if self.killed:
            return False, "kill switch active"

        balance = self._balance()
        pnl = self._daily_pnl()
        if self.daily_loss_pct > 0 and pnl <= -balance * self.daily_loss_pct / 100.0:
            return False, f"daily loss limit reached ({pnl:+.2f})"
        if self.daily_profit_pct > 0 and pnl >= balance * self.daily_profit_pct / 100.0:
            return False, f"daily profit target reached ({pnl:+.2f})"

        if self._open_count() >= self.max_positions:
            return False, f"max concurrent positions ({self.max_positions}) reached"

        if not self._in_session():
            return False, "outside trading session window"

        tick = mt5.symbol_info_tick(self.symbol)
        info = mt5.symbol_info(self.symbol)
        if tick is not None and info is not None and self.max_spread_frac > 0 and signal.sl_distance > 0:
            spread = tick.ask - tick.bid
            if spread > self.max_spread_frac * signal.sl_distance:
                return False, f"spread {spread:.{info.digits}f} too wide vs SL {signal.sl_distance:.{info.digits}f}"

        return True, ""

    def _in_session(self) -> bool:
        if self.session_start == 0 and self.session_end >= 24:
            return True
        h = datetime.now(timezone.utc).hour
        s, e = self.session_start, self.session_end
        if s <= e:
            return s <= h < e
        return h >= s or h < e

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _balance(self) -> float:
        info = self.connector.get_account_info()
        if info:
            return float(info.get("balance", _DEFAULT_BALANCE))
        return _DEFAULT_BALANCE

    def _daily_pnl(self) -> float:
        if self.mode == "PAPER":
            return self._day_realized
        return self._balance() - self._day_start_balance

    def _open_count(self) -> int:
        if self.mode == "PAPER":
            return self._paper.count()
        positions = mt5.positions_get(symbol=self.symbol) or []
        return sum(1 for p in positions if p.magic == AUTO_TRADE_MAGIC)

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._day != today:
            self._day = today
            self._day_realized = 0.0
            self._day_start_balance = self._balance()
            self._trades_today = 0

    def _emit_stats(self) -> None:
        self.stats_cb({
            "running": self.running,
            "killed": self.killed,
            "mode": self.mode,
            "daily_pnl": self._daily_pnl() if self.running else 0.0,
            "open_positions": self._open_count() if self.running else 0,
            "trades_today": self._trades_today,
        })

    def log(self, msg: str) -> None:
        self.log_cb(msg)
