"""Tracks the broker server clock's offset from UTC.

MT5 reports every time field (position/deal/order times, tick times) as epoch
seconds in the *server's* timezone, not UTC. To display correct times — and to
query history over the intended UTC range — we estimate the server offset by
comparing fresh tick times (server clock) against the local UTC clock.

The raw difference is rounded to the nearest 30 minutes (all real timezone
offsets are multiples of that), which absorbs tick staleness of up to ~15
minutes and local clock drift. Because a tick's time is always <= "now" on the
server clock, stale ticks can only under-estimate the offset — so we keep the
maximum value observed since the last reset. If no plausible estimate has been
seen (e.g. weekend with no fresh ticks), the offset is 0, i.e. times are
treated as UTC, matching the app's previous behavior.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

_HALF_HOUR = 1800
_MAX_OFFSET = 14 * 3600  # real timezones span UTC-12 .. UTC+14

# Liquid symbols to probe right after connecting; BTCUSD ticks on weekends too
_CALIBRATION_SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD")

_offset_seconds: int | None = None


def reset() -> None:
    global _offset_seconds
    _offset_seconds = None


def update_from_tick_time(server_ts: float) -> None:
    """Refine the offset estimate from a tick's server-time epoch."""
    global _offset_seconds
    raw = server_ts - time.time()
    rounded = int(round(raw / _HALF_HOUR)) * _HALF_HOUR
    if abs(rounded) > _MAX_OFFSET:
        return
    if _offset_seconds is None or rounded > _offset_seconds:
        _offset_seconds = rounded


def calibrate() -> None:
    """Best-effort estimate right after connecting: probe ticks for the
    symbols of open positions first, then a few liquid fallbacks."""
    if not MT5_AVAILABLE:
        return
    symbols: list[str] = []
    positions = mt5.positions_get()
    if positions:
        symbols.extend(p.symbol for p in positions)
    symbols.extend(_CALIBRATION_SYMBOLS)
    for sym in dict.fromkeys(symbols):
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            continue
        ts = tick.time_msc / 1000.0 if getattr(tick, "time_msc", 0) else tick.time
        update_from_tick_time(ts)
        if _offset_seconds is not None:
            return


def offset_seconds() -> int:
    return _offset_seconds or 0


def server_ts_to_utc(server_ts: float) -> datetime:
    """Convert an MT5 server-time epoch to a UTC-aware datetime."""
    return datetime.fromtimestamp(server_ts - offset_seconds(), tz=timezone.utc)


def utc_to_server_dt(dt: datetime) -> datetime:
    """Shift a UTC-aware datetime forward by the server offset so the MT5
    history API (which compares against server-time epochs) covers the
    intended UTC range."""
    return dt + timedelta(seconds=offset_seconds())
