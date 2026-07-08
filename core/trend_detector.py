"""Classify a symbol's recent price action as a clear trend or choppy.

Pure function of closed bars (no MT5, no Qt) so it's testable offline. Uses
ADX for trend strength and +DI/-DI plus an EMA filter for direction, with RSI
relative to its 50 midline as a second directional confirmation (RSI > 50 =
up bias, RSI < 50 = down bias). A trend is only "clear" when strength and both
direction signals agree; otherwise it's CHOPPY.

Hysteresis: entering a trend requires the strict thresholds (ADX >= entry,
RSI beyond 50±band), but an *established* trend (passed via `prev_state`)
holds on relaxed ones (ADX >= exit, RSI not across the opposite band edge).
This stops the state — and transition alerts — from flip-flapping when a
value hovers at a threshold.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from core import indicators

UP = "UP"
DOWN = "DOWN"
CHOPPY = "CHOPPY"
UNKNOWN = "UNKNOWN"

DEFAULT_ADX_PERIOD = 14
DEFAULT_EMA_PERIOD = 50
DEFAULT_RSI_PERIOD = 14
DEFAULT_ADX_THRESHOLD = 25.0   # ADX required to ENTER a clear trend
ADX_EXIT_THRESHOLD = 20.0      # an established trend holds until ADX drops below this
RSI_MIDLINE = 50.0
RSI_BAND = 2.0                 # enter needs RSI beyond 50±band; hold ends past the opposite edge


@dataclass
class TrendReading:
    state: str          # UP / DOWN / CHOPPY / UNKNOWN
    adx: float
    plus_di: float
    minus_di: float
    rsi: float = float("nan")
    price: float = float("nan")   # last closed-bar close
    ema: float = float("nan")     # EMA(DEFAULT_EMA_PERIOD) at that bar

    @property
    def is_clear(self) -> bool:
        return self.state in (UP, DOWN)


def detect(
    bars,
    adx_period: int = DEFAULT_ADX_PERIOD,
    ema_period: int = DEFAULT_EMA_PERIOD,
    adx_threshold: float = DEFAULT_ADX_THRESHOLD,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    prev_state: str | None = None,
) -> TrendReading:
    nan = float("nan")
    need = max(2 * adx_period + 1, ema_period + 1, rsi_period + 1)
    if bars is None or len(bars) < need:
        return TrendReading(UNKNOWN, nan, nan, nan, nan)

    high, low, close = bars["high"], bars["low"], bars["close"]
    adx_a, pdi_a, mdi_a = indicators.adx(high, low, close, adx_period)
    ema = indicators.ema(close, ema_period)
    rsi = float(indicators.rsi(close, rsi_period)[-1])

    adx = float(adx_a[-1])
    pdi = float(pdi_a[-1])
    mdi = float(mdi_a[-1])
    if not (math.isfinite(adx) and math.isfinite(pdi) and math.isfinite(mdi)):
        return TrendReading(UNKNOWN, adx, pdi, mdi, rsi)

    price = float(close[-1])
    ema_now = float(ema[-1])

    def _reading(state: str) -> TrendReading:
        return TrendReading(state, adx, pdi, mdi, rsi, price, ema_now)

    up_dir = pdi > mdi and price > ema_now
    down_dir = mdi > pdi and price < ema_now

    # Entry — strict thresholds must all agree
    if adx >= adx_threshold:
        if up_dir and rsi > RSI_MIDLINE + RSI_BAND:
            return _reading(UP)
        if down_dir and rsi < RSI_MIDLINE - RSI_BAND:
            return _reading(DOWN)

    # Hold (hysteresis) — an established trend persists on relaxed thresholds,
    # so hovering at ADX≈entry or RSI≈50 doesn't flip the state every bar
    if (prev_state == UP and adx >= ADX_EXIT_THRESHOLD
            and up_dir and rsi > RSI_MIDLINE - RSI_BAND):
        return _reading(UP)
    if (prev_state == DOWN and adx >= ADX_EXIT_THRESHOLD
            and down_dir and rsi < RSI_MIDLINE + RSI_BAND):
        return _reading(DOWN)

    return _reading(CHOPPY)
