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
