"""Position sizing from account-risk percentage.

Sizing uses the symbol's tick value/size so the money risked if the stop is
hit equals `balance * risk_pct%`, regardless of the symbol's contract spec.
The result is snapped down to the symbol's volume_step and clamped to
[volume_min, volume_max]. The per-trade guardrails (spread/session/daily
limits/max positions) live on AutoTrader, which has the live market state.
"""
from __future__ import annotations

import math


class RiskManager:
    def __init__(self, risk_pct: float = 0.5) -> None:
        self.risk_pct = risk_pct

    def size_lots(self, balance: float, symbol_info, sl_distance: float) -> float:
        if symbol_info is None or sl_distance <= 0 or balance <= 0 or self.risk_pct <= 0:
            return 0.0

        tick_value = getattr(symbol_info, "trade_tick_value", 0.0)
        tick_size = getattr(symbol_info, "trade_tick_size", 0.0)
        if tick_value <= 0 or tick_size <= 0:
            return 0.0

        risk_money = balance * self.risk_pct / 100.0
        loss_per_lot = sl_distance / tick_size * tick_value
        if loss_per_lot <= 0:
            return 0.0

        lots = risk_money / loss_per_lot

        step = getattr(symbol_info, "volume_step", 0.01) or 0.01
        vol_min = getattr(symbol_info, "volume_min", 0.01)
        vol_max = getattr(symbol_info, "volume_max", 100.0)

        lots = math.floor(lots / step + 1e-9) * step
        lots = round(lots, 8)
        if lots < vol_min:
            return 0.0
        return min(lots, vol_max)
