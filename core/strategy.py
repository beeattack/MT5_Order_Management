"""Trading strategies. A strategy is a pure function of closed bars →
Signal | None, so it can be unit-tested and backtested without MT5.

`evaluate` receives the NumPy structured array returned by
`mt5.copy_rates_*` (fields: time, open, high, low, close, tick_volume, ...),
already trimmed to *closed* bars only — never the still-forming bar.
"""
from __future__ import annotations

import numpy as np

from core import indicators
from models.signal import Signal


class EmaRsiPullbackStrategy:
    """Trend-filtered pullback scalp.

    - Trend filter: only long above EMA(trend), only short below.
    - Trigger: RSI crossing back up through `rsi_low` (long) or down through
      `rsi_high` (short) — a pullback resuming in the trend direction.
    - Stop: `atr_mult * ATR(atr_period)`. Target: `rr * stop`.
    """

    def __init__(
        self,
        ema_trend: int = 50,
        rsi_period: int = 7,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        atr_period: int = 14,
        atr_mult: float = 1.5,
        rr: float = 1.5,
    ) -> None:
        self.ema_trend = ema_trend
        self.rsi_period = rsi_period
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.rr = rr

    @property
    def min_bars(self) -> int:
        return max(self.ema_trend, self.atr_period) + 2

    def evaluate(self, bars: np.ndarray) -> Signal | None:
        if bars is None or len(bars) < self.min_bars:
            return None

        close = bars["close"]
        ema_trend = indicators.ema(close, self.ema_trend)
        rsi = indicators.rsi(close, self.rsi_period)
        atr = indicators.atr(bars["high"], bars["low"], close, self.atr_period)

        price = float(close[-1])
        atr_now = float(atr[-1])
        if not np.isfinite(atr_now) or atr_now <= 0:
            return None

        sl = atr_now * self.atr_mult
        tp = sl * self.rr

        uptrend = price > ema_trend[-1]
        downtrend = price < ema_trend[-1]
        rsi_cross_up = rsi[-2] < self.rsi_low <= rsi[-1]
        rsi_cross_down = rsi[-2] > self.rsi_high >= rsi[-1]

        if uptrend and rsi_cross_up:
            return Signal("BUY", sl, tp, f"Uptrend + RSI cross up ({rsi[-1]:.1f})")
        if downtrend and rsi_cross_down:
            return Signal("SELL", sl, tp, f"Downtrend + RSI cross down ({rsi[-1]:.1f})")
        return None
