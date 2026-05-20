from __future__ import annotations

from datetime import datetime

from models.history_entry import HistoryEntry

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False


class HistoryManager:
    def get_history(self, from_dt: datetime, to_dt: datetime) -> list[HistoryEntry]:
        if not MT5_AVAILABLE:
            return []

        deals = mt5.history_deals_get(from_dt, to_dt)
        if deals is None:
            return []

        entries: list[HistoryEntry] = []
        for deal in deals:
            # Only process closing deals with a known symbol
            if deal.entry != mt5.DEAL_ENTRY_OUT:
                continue
            if deal.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                continue
            if not deal.symbol:
                continue

            # DEAL_TYPE_SELL closes a BUY position; DEAL_TYPE_BUY closes a SELL position
            order_type = "BUY" if deal.type == mt5.DEAL_TYPE_SELL else "SELL"

            close_time = datetime.fromtimestamp(deal.time)

            # Try to resolve open_time and open_price from the originating order
            open_time = close_time
            open_price = deal.price
            if deal.order:
                orig_orders = mt5.history_orders_get(ticket=deal.order)
                if orig_orders:
                    open_time = datetime.fromtimestamp(orig_orders[0].time_setup)
                    open_price = orig_orders[0].price_open

            entries.append(HistoryEntry(
                ticket=deal.ticket,
                symbol=deal.symbol,
                order_type=order_type,
                volume=deal.volume,
                open_price=open_price,
                close_price=deal.price,
                profit=deal.profit,
                open_time=open_time,
                close_time=close_time,
                is_win=deal.profit > 0,
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
