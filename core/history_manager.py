from __future__ import annotations

from datetime import datetime

from core import server_clock
from core.constants import AUTO_TRADE_MAGIC
from models.history_entry import HistoryEntry

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False


class HistoryManager:
    def __init__(self) -> None:
        self._digits_cache: dict[str, int] = {}

    def _symbol_digits(self, symbol: str) -> int:
        digits = self._digits_cache.get(symbol)
        if digits is None:
            info = mt5.symbol_info(symbol)
            digits = info.digits if info is not None else 2
            self._digits_cache[symbol] = digits
        return digits

    def get_history(self, from_dt: datetime, to_dt: datetime) -> list[HistoryEntry]:
        if not MT5_AVAILABLE:
            return []

        # MT5 compares against server-time epochs — shift the UTC range
        deals = mt5.history_deals_get(
            server_clock.utc_to_server_dt(from_dt),
            server_clock.utc_to_server_dt(to_dt),
        )
        if deals is None:
            return []

        out_entries = {mt5.DEAL_ENTRY_OUT, getattr(mt5, "DEAL_ENTRY_OUT_BY", mt5.DEAL_ENTRY_OUT)}

        # Index entry deals by position so each closing deal can resolve its
        # open time/price without a per-deal history query
        entry_deals: dict[int, list] = {}
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_IN and d.position_id:
                entry_deals.setdefault(d.position_id, []).append(d)

        entries: list[HistoryEntry] = []
        for deal in deals:
            # Only process closing deals with a known symbol
            if deal.entry not in out_entries:
                continue
            if deal.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                continue
            if not deal.symbol:
                continue

            # DEAL_TYPE_SELL closes a BUY position; DEAL_TYPE_BUY closes a SELL position
            order_type = "BUY" if deal.type == mt5.DEAL_TYPE_SELL else "SELL"

            close_time = server_clock.server_ts_to_utc(deal.time)

            # Resolve open_time/open_price from the position's first entry deal.
            # If the position was opened before the queried range, its entry
            # deal isn't in `deals` — fetch that position's deals once.
            open_time = close_time
            open_price = deal.price
            # The opening order carries the auto-trade magic; the closing deal
            # may not, so classify from the entry deal when we have it.
            entry_magic = deal.magic
            if deal.position_id:
                ins = entry_deals.get(deal.position_id)
                if ins is None:
                    pos_deals = mt5.history_deals_get(position=deal.position_id)
                    ins = [d for d in (pos_deals or []) if d.entry == mt5.DEAL_ENTRY_IN]
                    entry_deals[deal.position_id] = ins
                if ins:
                    first_in = min(ins, key=lambda d: d.time)
                    open_time = server_clock.server_ts_to_utc(first_in.time)
                    open_price = first_in.price
                    entry_magic = first_in.magic

            # Net result of this closing deal (commission/swap/fee included)
            net_profit = deal.profit + deal.commission + deal.swap + getattr(deal, "fee", 0.0)

            entries.append(HistoryEntry(
                ticket=deal.ticket,
                symbol=deal.symbol,
                order_type=order_type,
                volume=deal.volume,
                open_price=open_price,
                close_price=deal.price,
                profit=net_profit,
                open_time=open_time,
                close_time=close_time,
                is_win=net_profit > 0,
                digits=self._symbol_digits(deal.symbol),
                is_auto=(entry_magic == AUTO_TRADE_MAGIC),
                position_id=deal.position_id,
            ))

        # Sort newest first
        entries.sort(key=lambda e: e.close_time, reverse=True)
        return entries

    def calculate_win_rate(self, entries: list[HistoryEntry]) -> float:
        total = len(entries)
        if total == 0:
            return 0.0
        wins = sum(1 for e in entries if e.is_win)
        return wins / total * 100

    def calculate_summary(self, entries: list[HistoryEntry]) -> dict:
        total = len(entries)
        wins = sum(1 for e in entries if e.is_win)
        losses = total - wins
        net_profit = sum(e.profit for e in entries)
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "net_profit": net_profit,
        }
