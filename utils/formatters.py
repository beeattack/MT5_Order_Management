from __future__ import annotations

from datetime import datetime


def format_profit(value: float) -> str:
    if value >= 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_volume(value: float) -> str:
    return f"{value:.2f}"


def format_price(value: float) -> str:
    return f"{value:.5f}"


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_win_rate(rate: float) -> str:
    return f"{rate:.1f}%"
