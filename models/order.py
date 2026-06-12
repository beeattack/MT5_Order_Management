from dataclasses import dataclass
from datetime import datetime


@dataclass
class Order:
    ticket: int
    symbol: str
    order_type: str     # "BUY" or "SELL"
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    open_time: datetime
    digits: int = 2     # price decimal places from symbol_info
