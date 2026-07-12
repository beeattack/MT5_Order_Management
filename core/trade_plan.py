"""Daily trade-plan logic: risk what you last made, aim for double.

The plan takes the most recent *profitable* trading day (walking backwards
through closed-trade history, skipping losing / empty days), uses that day's
net profit as the base for today's maximum drawdown, and sets today's profit
target at 2x the (percentage-adjusted) drawdown limit.

Pure functions of HistoryEntry lists (no MT5, no Qt) so it's testable offline.
Days are UTC calendar days, consistent with the dashboard's "Today" period.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

LOOKBACK_DAYS = 30

# Status codes for today's P/L vs the plan
ACTIVE = "ACTIVE"            # trading day in progress, within limits
LIMIT_HIT = "LIMIT_HIT"      # today's P/L breached the drawdown limit
TARGET_REACHED = "TARGET"    # today's P/L reached the target


@dataclass
class BaseDay:
    day: date          # the profitable day the plan is built on
    profit: float      # that day's net profit (> 0)
    days_ago: int      # 1 = yesterday
    skipped: int       # losing/empty days skipped before finding it


def today_range_utc(now: datetime) -> tuple[datetime, datetime]:
    """(midnight_utc, now) for the current UTC day."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def lookback_range_utc(now: datetime, days: int = LOOKBACK_DAYS) -> tuple[datetime, datetime]:
    """(midnight_utc - days, midnight_utc): the window to search for a base day."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=days), midnight


def find_base_day(entries, now: datetime) -> BaseDay | None:
    """Most recent UTC day *before today* with positive net profit.

    `entries` are HistoryEntry-like objects (need .profit and .close_time)
    from the lookback window; days with no trades or net <= 0 are skipped.
    """
    today = now.date()
    by_day: dict[date, float] = {}
    for e in entries:
        d = e.close_time.astimezone(timezone.utc).date()
        if d < today:
            by_day[d] = by_day.get(d, 0.0) + e.profit

    skipped = 0
    for day in sorted(by_day, reverse=True):
        if by_day[day] > 0:
            return BaseDay(
                day=day,
                profit=by_day[day],
                days_ago=(today - day).days,
                skipped=skipped,
            )
        skipped += 1
    return None


def drawdown_limit(base_profit: float, dd_pct: int) -> float:
    """Today's max drawdown (positive number) from the base profit and the
    user's percentage setting."""
    return base_profit * dd_pct / 100.0


def profit_target(limit: float) -> float:
    """Today's profit target: 2x the drawdown limit (risk X to make 2X)."""
    return 2.0 * limit


def plan_status(today_pl: float, limit: float, target: float) -> str:
    """Classify today's total P/L against the plan."""
    if limit > 0 and today_pl <= -limit:
        return LIMIT_HIT
    if target > 0 and today_pl >= target:
        return TARGET_REACHED
    return ACTIVE
