"""Pure NumPy technical indicators used by strategies.

All functions take/return 1-D arrays aligned to the input length so callers
can index by bar position. They are deterministic and MT5-free, which keeps
strategies unit-testable and backtestable offline.
"""
from __future__ import annotations

import numpy as np


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average, seeded with the first value."""
    values = np.asarray(values, dtype=float)
    out = np.empty_like(values)
    if len(values) == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's RSI. Values before enough data exists are filled with 50
    (neutral) so callers can index without bounds checks."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    out = np.full(n, 50.0)
    if n <= period:
        return out

    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1 + rs)
    return out


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's Average True Range. Leading values (before `period` bars) are
    NaN so callers can detect insufficient data."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out

    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))

    out[period] = tr[1:period + 1].mean()
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14):
    """Wilder's ADX with +DI / -DI — measures trend *strength* (ADX) and
    *direction* (which DI dominates). Returns (adx, plus_di, minus_di), each
    aligned to the input length with NaN where undefined.

    ADX >= ~25 conventionally signals a trending market; below ~20 a choppy /
    ranging one. Needs at least 2*period+1 bars to produce a value.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    n = len(close)
    adx_out = np.full(n, np.nan)
    pdi_out = np.full(n, np.nan)
    mdi_out = np.full(n, np.nan)
    if n < 2 * period + 1:
        return adx_out, pdi_out, mdi_out

    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev_close = close[:-1]
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)))

    m = len(tr)  # n - 1

    def _wilder(x: np.ndarray) -> np.ndarray:
        s = np.full(m, np.nan)
        s[period - 1] = x[:period].sum()
        for i in range(period, m):
            s[i] = s[i - 1] - s[i - 1] / period + x[i]
        return s

    str_ = _wilder(tr)
    spdm = _wilder(plus_dm)
    smdm = _wilder(minus_dm)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * spdm / str_
        mdi = 100.0 * smdm / str_
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)

    adx_arr = np.full(m, np.nan)
    start = period - 1            # first valid DX index
    first_adx = start + period    # need `period` DX values to seed the average
    if first_adx <= m:
        adx_arr[first_adx - 1] = np.nanmean(dx[start:start + period])
        for i in range(first_adx, m):
            adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

    pdi_out[1:] = pdi
    mdi_out[1:] = mdi
    adx_out[1:] = adx_arr
    return adx_out, pdi_out, mdi_out
