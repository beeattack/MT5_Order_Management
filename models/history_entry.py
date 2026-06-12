from dataclasses import dataclass
from datetime import datetime


@dataclass
class HistoryEntry:
    ticket: int
    symbol: str
    order_type: str     # "BUY" or "SELL"
    volume: float
    open_price: float
    close_price: float
    profit: float
    open_time: datetime
    close_time: datetime
    is_win: bool        # profit > 0 (net of commission/swap/fee)
    digits: int = 2     # price decimal places from symbol_info
