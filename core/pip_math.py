"""Pip arithmetic shared by every order list.

MT5 quotes a symbol with `digits` decimals, so one point is 10**-digits. A
*pip* is the unit traders actually count, and it is not always a point: on the
two fractional-pip quote shapes MT5 uses -- 5-digit FX (1.08523) and 3-digit
JPY crosses (150.123) -- the last decimal is a tenth of a pip, so a pip is ten
points. Every other shape (4-digit FX, 2-digit metals and indices) quotes a
pip in its last decimal, so there a pip is one point.
"""
from __future__ import annotations

# Quote shapes whose last decimal is a tenth of a pip
FRACTIONAL_PIP_DIGITS = frozenset((3, 5))


def pip_size(digits: int) -> float:
    """Price distance of one pip for a symbol quoted with *digits* decimals."""
    if digits < 0:
        return 0.0
    point = 10.0 ** -digits
    return point * 10.0 if digits in FRACTIONAL_PIP_DIGITS else point


def pips_from_entry(open_price: float, current_price: float,
                    order_type: str, digits: int) -> float:
    """Signed distance from the entry price in pips.

    Positive when price has moved the position's way, negative when it has
    moved against it -- so the sign always agrees with the row's profit.
    """
    size = pip_size(digits)
    if size <= 0 or not open_price:
        return 0.0
    delta = current_price - open_price
    if order_type == "SELL":
        delta = -delta
    return delta / size


def format_pips(value: float) -> str:
    """Signed pip count, kept narrow enough for the compact and ghost rows:
    one decimal while it is worth having, whole pips once past 100."""
    sign = "+" if value >= 0 else "-"
    mag = abs(value)
    return f"{sign}{mag:,.1f}" if mag < 100 else f"{sign}{mag:,.0f}"
