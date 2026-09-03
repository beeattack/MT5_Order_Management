"""Convert an account-currency amount into Thai baht using the broker's own
quotes.

The rate comes from whatever THB pair the connected broker actually lists, so
no network call and no hard-coded rate. Symbol names vary between brokers
(USDTHB, USDTHB#, USDTHB.m ...), so pairs are matched on their letters only.

Not every broker quotes THB at all — it isn't freely deliverable offshore, and
every route here has to end at a THB quote, so a terminal without one has no
route regardless of how many USD pairs it carries. For that case the caller can
supply a manual rate, used only when the automatic lookup finds nothing.

Runs on the main thread with every other MT5 call. Rates are cached briefly
because a dashboard refresh asks for the same pair repeatedly.
"""
from __future__ import annotations

import time

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

THB = "THB"
_CACHE_TTL = 30.0                      # seconds
_cache: dict[str, tuple[float, float, str]] = {}   # pair -> (rate, fetched_at, symbol)


def _letters(name: str) -> str:
    return "".join(ch for ch in name.upper() if ch.isalpha())


def _find_symbol(pair: str) -> str | None:
    """Broker symbol quoting *pair* (e.g. "USDTHB"), suffixes tolerated."""
    try:
        symbols = mt5.symbols_get()
    except Exception:
        symbols = None
    if not symbols:
        return None
    matches = [s.name for s in symbols if _letters(s.name) == pair]
    if not matches:
        # some brokers pad the name, e.g. "USDTHB.raw" -> letters "USDTHBRAW"
        matches = [s.name for s in symbols if _letters(s.name).startswith(pair)]
    # prefer the shortest (plainest) name, and one already in Market Watch
    matches.sort(key=lambda n: (not getattr(mt5.symbol_info(n), "visible", False), len(n)))
    return matches[0] if matches else None


def _quote(pair: str) -> tuple[float, str] | None:
    """Current price of *pair* plus the broker symbol it came from."""
    if not MT5_AVAILABLE:
        return None
    hit = _cache.get(pair)
    if hit and time.time() - hit[1] < _CACHE_TTL:
        return (hit[0], hit[2]) if hit[0] > 0 else None

    rate, name = 0.0, ""
    symbol = _find_symbol(pair)
    if symbol:
        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
        except Exception:
            tick = None
        if tick is not None:
            # mid price: the amount is notional, not an order being filled
            bid, ask = float(tick.bid), float(tick.ask)
            if bid > 0 and ask > 0:
                rate = (bid + ask) / 2
            elif bid > 0:
                rate = bid
        name = symbol

    _cache[pair] = (rate, time.time(), name)
    return (rate, name) if rate > 0 else None


def broker_rate(currency: str) -> tuple[float, str] | None:
    """Live rate taking one unit of *currency* to THB, from broker quotes."""
    currency = (currency or "").upper()
    if not currency or not MT5_AVAILABLE:
        return None
    if currency == THB:
        return 1.0, "account is already in THB"

    direct = _quote(currency + THB)
    if direct:
        rate, sym = direct
        return rate, f"{sym} {rate:,.4f}"

    inverse = _quote(THB + currency)
    if inverse:
        rate, sym = inverse
        return 1.0 / rate, f"1 / {sym} {rate:,.4f}"

    # cross: convert to USD first, then USD -> THB
    usd_thb = _quote("USD" + THB)
    if usd_thb:
        leg = _quote(currency + "USD")
        if leg:
            rate, sym = leg
            per_usd = rate
        else:
            leg = _quote("USD" + currency)
            if not leg:
                return None
            rate, sym = leg
            per_usd = 1.0 / rate
        thb_rate, thb_sym = usd_thb
        return per_usd * thb_rate, f"via {sym} × {thb_sym} {thb_rate:,.4f}"
    return None


def to_thb(amount: float, currency: str,
           manual_rate: float | None = None) -> tuple[float, str] | None:
    """*amount* in *currency* converted to THB.

    Returns (baht, note) where note names the rate used, or None when there is
    neither a broker route nor a usable manual rate. Broker quotes always win;
    *manual_rate* (THB per unit of *currency*) is the fallback for terminals
    that quote no THB pair at all.
    """
    live = broker_rate(currency)
    if live:
        rate, note = live
        return amount * rate, note
    if manual_rate and manual_rate > 0:
        return amount * float(manual_rate), f"{manual_rate:,.4f} (manual)"
    return None
