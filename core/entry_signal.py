"""Pullback-entry signal: flag the bar where a pullback inside an
established trend ends — a good moment to enter *with* the trend.

Pure function of closed bars (no MT5, no Qt), same contract as
`trend_detector`. The regime comes from ADX with +DI/−DI, the bias from
the slow RSI vs its 50 midline, and the *timing* from the fast RSI:

BUY  — ADX >= threshold, +DI > −DI, slow RSI > 50, the fast RSI dipped
       into the pullback zone recently, and on this bar it recovers up
       through the recovery level without already being overbought.
SELL — the mirror image.

(The trigger is the fast RSI re-crossing a fixed recovery level, not the
slow RSI: after a long trend the slow RSI stays so elevated that the
fast one only catches it near the *end* of the resumption move.)

The crossing condition can only hold on the bar where the cross happens,
so the signal is inherently transition-based. Callers still must dedupe
across polls: the same closed bar keeps re-evaluating true until the
next bar closes (see WatchlistMonitor's bar-time cooldown).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core import indicators

BUY = "BUY"
SELL = "SELL"
NONE = "NONE"

FAST_RSI_PERIOD = 9
SLOW_RSI_PERIOD = 14
ADX_PERIOD = 14
ADX_THRESHOLD = 25.0       # same regime bar as the trend detector's entry
PULLBACK_LOOKBACK = 10     # bars in which the fast RSI must have dipped/spiked
PULLBACK_BUY = 40.0        # fast RSI must have touched <= this for a BUY
PULLBACK_SELL = 60.0       # fast RSI must have touched >= this for a SELL
RECOVERY_BUY = 45.0        # BUY fires when the fast RSI crosses back above this
RECOVERY_SELL = 55.0       # SELL fires when the fast RSI crosses back below this
OVEREXTENDED_BUY = 70.0    # skip a BUY whose cross lands already overbought
OVEREXTENDED_SELL = 30.0   # skip a SELL whose cross lands already oversold


@dataclass
class EntryReading:
    state: str = NONE               # BUY / SELL / NONE
    rsi_fast: float = float("nan")  # RSI(FAST_RSI_PERIOD) at the last closed bar
    rsi_slow: float = float("nan")
    adx: float = float("nan")
    plus_di: float = float("nan")
    minus_di: float = float("nan")

    @property
    def is_signal(self) -> bool:
        return self.state in (BUY, SELL)


def detect_entry(bars, adx_rising: bool = False) -> EntryReading:
    """Classify the last closed bar of *bars* as a BUY/SELL entry or NONE.

    `adx_rising=True` additionally requires ADX to be rising bar-over-bar
    (fewer, higher-quality signals).
    """
    need = max(2 * ADX_PERIOD + 1, SLOW_RSI_PERIOD + PULLBACK_LOOKBACK + 1)
    if bars is None or len(bars) < need:
        return EntryReading()

    high, low, close = bars["high"], bars["low"], bars["close"]
    rsi_f = indicators.rsi(close, FAST_RSI_PERIOD)
    rsi_s = indicators.rsi(close, SLOW_RSI_PERIOD)
    adx_a, pdi_a, mdi_a = indicators.adx(high, low, close, ADX_PERIOD)

    rf, rs = float(rsi_f[-1]), float(rsi_s[-1])
    adx, pdi, mdi = float(adx_a[-1]), float(pdi_a[-1]), float(mdi_a[-1])
    reading = EntryReading(NONE, rf, rs, adx, pdi, mdi)

    if not (math.isfinite(adx) and math.isfinite(pdi) and math.isfinite(mdi)):
        return reading
    if adx < ADX_THRESHOLD:
        return reading
    if adx_rising and not (math.isfinite(float(adx_a[-2])) and adx > float(adx_a[-2])):
        return reading

    recovered_up = rsi_f[-2] < RECOVERY_BUY <= rf
    recovered_dn = rsi_f[-2] > RECOVERY_SELL >= rf
    # the dip/spike must have happened on the bars *before* the signal bar
    prior_fast = rsi_f[-1 - PULLBACK_LOOKBACK:-1]

    if (pdi > mdi and rs > 50.0 and recovered_up
            and float(prior_fast.min()) <= PULLBACK_BUY
            and rf < OVEREXTENDED_BUY):
        reading.state = BUY
    elif (mdi > pdi and rs < 50.0 and recovered_dn
            and float(prior_fast.max()) >= PULLBACK_SELL
            and rf > OVEREXTENDED_SELL):
        reading.state = SELL
    return reading
