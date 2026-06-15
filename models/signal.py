from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Signal:
    """A trade instruction emitted by a strategy. SL/TP are *distances* in
    price units; the executor turns them into absolute prices off the fill."""
    direction: str        # "BUY" or "SELL"
    sl_distance: float    # stop distance in price units
    tp_distance: float    # target distance in price units
    reason: str           # human-readable explanation for the decision log


@dataclass
class PaperPosition:
    """A simulated position tracked in paper mode."""
    symbol: str
    direction: str        # "BUY" or "SELL"
    volume: float
    entry_price: float
    sl_price: float
    tp_price: float
    open_bar_time: int     # server-epoch bar time the position was opened on
