"""Trade-performance analytics. Pure functions over a list of HistoryEntry
(closing deals) — no Qt, no MT5 — so they're unit-testable and backtestable.

Closing deals are first grouped into position-level Trades (a position closed
in several partials is one trade, not several), then all statistics, the
closed-trade equity curve, breakdowns, and the rule-based insights are derived
from that. Profit is already net of commission/swap/fee (set by HistoryManager).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

from models.history_entry import HistoryEntry

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Sample-size gates so insights are not drawn from noise
_MIN_SAMPLE = 10    # overall, before any insight fires
_MIN_GROUP = 8      # per symbol / direction / source
_MIN_BUCKET = 6     # per weekday / hour


@dataclass
class Trade:
    """One position, aggregated from its closing deal(s)."""
    position_id: int
    symbol: str
    direction: str          # "BUY" / "SELL"
    volume: float
    profit: float           # net, summed across partial closes
    open_time: datetime
    close_time: datetime
    is_auto: bool


@dataclass
class GroupStats:
    label: str
    trades: int
    wins: int
    win_rate: float
    net_profit: float
    profit_factor: float


@dataclass
class Insight:
    title: str
    finding: str
    suggestion: str
    severity: str           # "critical" | "warning" | "good" | "info"
    impact: float = 0.0     # abs P&L magnitude, for ranking


@dataclass
class PerformanceStats:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0        # positive magnitude
    payoff_ratio: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0    # negative
    max_consec_wins: int = 0
    max_consec_losses: int = 0
    max_drawdown: float = 0.0
    recovery_factor: float = 0.0
    avg_hold_secs: float = 0.0
    avg_hold_win_secs: float = 0.0
    avg_hold_loss_secs: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    equity_times: list[datetime] = field(default_factory=list)
    by_symbol: list[GroupStats] = field(default_factory=list)
    by_direction: list[GroupStats] = field(default_factory=list)
    by_source: list[GroupStats] = field(default_factory=list)
    by_weekday: list[GroupStats] = field(default_factory=list)
    by_hour: list[GroupStats] = field(default_factory=list)


def group_trades(entries: list[HistoryEntry]) -> list[Trade]:
    """Aggregate closing deals into position-level trades."""
    buckets: dict[int, list[HistoryEntry]] = {}
    for e in entries:
        key = e.position_id or e.ticket
        buckets.setdefault(key, []).append(e)

    trades: list[Trade] = []
    for key, rows in buckets.items():
        first = rows[0]
        trades.append(Trade(
            position_id=key,
            symbol=first.symbol,
            direction=first.order_type,
            volume=sum(r.volume for r in rows),
            profit=sum(r.profit for r in rows),
            open_time=min(r.open_time for r in rows),
            close_time=max(r.close_time for r in rows),
            is_auto=first.is_auto,
        ))
    return trades


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else 0.0


def _group_stats(label: str, trades: list[Trade]) -> GroupStats:
    n = len(trades)
    wins = sum(1 for t in trades if t.profit > 0)
    net = sum(t.profit for t in trades)
    gp = sum(t.profit for t in trades if t.profit > 0)
    gl = -sum(t.profit for t in trades if t.profit <= 0)
    return GroupStats(
        label=label,
        trades=n,
        wins=wins,
        win_rate=(wins / n * 100) if n else 0.0,
        net_profit=net,
        profit_factor=_profit_factor(gp, gl),
    )


def compute(entries: list[HistoryEntry]) -> PerformanceStats:
    trades = group_trades(entries)
    trades.sort(key=lambda t: t.close_time)
    n = len(trades)
    if n == 0:
        return PerformanceStats()

    profits = [t.profit for t in trades]
    wins_list = [p for p in profits if p > 0]
    losses_list = [p for p in profits if p <= 0]
    wins, losses = len(wins_list), len(losses_list)

    gross_profit = sum(wins_list)
    gross_loss = -sum(losses_list)
    net = sum(profits)

    avg_win = mean(wins_list) if wins_list else 0.0
    avg_loss = (gross_loss / losses) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else (math.inf if avg_win > 0 else 0.0)

    # consecutive streaks
    mcw = mcl = cw = cl = 0
    for p in profits:
        if p > 0:
            cw, cl = cw + 1, 0
        else:
            cl, cw = cl + 1, 0
        mcw, mcl = max(mcw, cw), max(mcl, cl)

    # closed-trade equity curve + max drawdown
    cum = peak = maxdd = 0.0
    curve: list[float] = []
    times: list[datetime] = []
    for t in trades:
        cum += t.profit
        curve.append(cum)
        times.append(t.close_time)
        peak = max(peak, cum)
        maxdd = max(maxdd, peak - cum)
    recovery = (net / maxdd) if maxdd > 0 else (math.inf if net > 0 else 0.0)

    holds = [(t.close_time - t.open_time).total_seconds() for t in trades]
    win_holds = [h for h, p in zip(holds, profits) if p > 0]
    loss_holds = [h for h, p in zip(holds, profits) if p <= 0]

    symbols = sorted({t.symbol for t in trades})
    by_symbol = sorted(
        (_group_stats(s, [t for t in trades if t.symbol == s]) for s in symbols),
        key=lambda g: g.net_profit,
    )
    by_direction = [
        _group_stats(d, [t for t in trades if t.direction == d])
        for d in ("BUY", "SELL") if any(t.direction == d for t in trades)
    ]
    by_source = []
    autos = [t for t in trades if t.is_auto]
    manuals = [t for t in trades if not t.is_auto]
    if autos:
        by_source.append(_group_stats("Auto", autos))
    if manuals:
        by_source.append(_group_stats("Manual", manuals))

    by_weekday = []
    for i, name in enumerate(_WEEKDAYS):
        bucket = [t for t in trades if t.close_time.weekday() == i]
        if bucket:
            by_weekday.append(_group_stats(name, bucket))
    by_hour = []
    for h in range(24):
        bucket = [t for t in trades if t.close_time.hour == h]
        if bucket:
            by_hour.append(_group_stats(f"{h:02d}:00", bucket))

    return PerformanceStats(
        total_trades=n,
        wins=wins,
        losses=losses,
        win_rate=wins / n * 100,
        net_profit=net,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=_profit_factor(gross_profit, gross_loss),
        expectancy=net / n,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff,
        largest_win=max(profits),
        largest_loss=min(profits),
        max_consec_wins=mcw,
        max_consec_losses=mcl,
        max_drawdown=maxdd,
        recovery_factor=recovery,
        avg_hold_secs=mean(holds) if holds else 0.0,
        avg_hold_win_secs=mean(win_holds) if win_holds else 0.0,
        avg_hold_loss_secs=mean(loss_holds) if loss_holds else 0.0,
        equity_curve=curve,
        equity_times=times,
        by_symbol=by_symbol,
        by_direction=by_direction,
        by_source=by_source,
        by_weekday=by_weekday,
        by_hour=by_hour,
    )


def insights(stats: PerformanceStats) -> list[Insight]:
    """Rule-based, descriptive coaching derived from the user's own history.

    Every rule is gated on sample size; nothing fires below _MIN_SAMPLE. These
    describe what happened — they are not predictions or trade advice.
    """
    n = stats.total_trades
    if n < _MIN_SAMPLE:
        return [Insight(
            "Not enough data yet",
            f"Only {n} trade(s) in this period — too few to judge reliably.",
            f"Collect at least {_MIN_SAMPLE} trades or widen the date range before reading the rest as signal.",
            "info",
        )]

    out: list[Insight] = []
    pf = stats.profit_factor

    # Overall edge
    if pf < 1.0:
        out.append(Insight(
            "System is net-losing this period",
            f"Profit factor {_fmt_pf(pf)} (gross profit ${stats.gross_profit:,.0f} vs gross loss ${stats.gross_loss:,.0f}).",
            "Pause size or paper-trade until the edge is positive; review which symbols/directions below are bleeding.",
            "critical", impact=stats.gross_loss,
        ))
    elif pf < 1.3:
        out.append(Insight(
            "Thin edge",
            f"Profit factor {_fmt_pf(pf)} — only marginally profitable; costs and slippage can erase it.",
            "Tighten trade selection and watch spread/commission as a share of each target.",
            "warning", impact=stats.gross_loss,
        ))
    else:
        out.append(Insight(
            "Healthy profit factor",
            f"Profit factor {_fmt_pf(pf)} with a {stats.win_rate:.0f}% win rate.",
            "Keep doing what works; scale risk only as the sample grows.",
            "good", impact=stats.net_profit,
        ))

    # Win-rate vs payoff mismatch
    if stats.losses >= _MIN_GROUP and 0 < stats.payoff_ratio < 1.0:
        out.append(Insight(
            "Losers are bigger than winners",
            f"Average win ${stats.avg_win:,.0f} vs average loss ${stats.avg_loss:,.0f} "
            f"(payoff {stats.payoff_ratio:.2f}, win rate {stats.win_rate:.0f}%).",
            "Cut losers sooner or let winners run — your weakness is trade management, not entries.",
            "warning", impact=stats.avg_loss * stats.losses,
        ))

    # Worst symbol drag
    losers = [g for g in stats.by_symbol if g.trades >= _MIN_GROUP and g.net_profit < 0 and g.profit_factor < 1.0]
    if losers:
        g = min(losers, key=lambda x: x.net_profit)
        out.append(Insight(
            f"{g.label} is dragging the account",
            f"{g.label}: net ${g.net_profit:,.0f} over {g.trades} trades, profit factor {_fmt_pf(g.profit_factor)}.",
            f"Cut size on {g.label} or drop it until it proves itself again.",
            "warning", impact=abs(g.net_profit),
        ))

    # Direction bias
    if len(stats.by_direction) == 2 and all(g.trades >= _MIN_GROUP for g in stats.by_direction):
        d = {g.label: g for g in stats.by_direction}
        for side, other in (("BUY", "SELL"), ("SELL", "BUY")):
            if d[side].profit_factor < 1.0 and d[other].profit_factor > 1.2:
                out.append(Insight(
                    f"Your {side} trades lose money",
                    f"{side} PF {_fmt_pf(d[side].profit_factor)} (net ${d[side].net_profit:,.0f}) vs "
                    f"{other} PF {_fmt_pf(d[other].profit_factor)} (net ${d[other].net_profit:,.0f}).",
                    f"You may be fighting the trend on {side}s — favor {other} setups or demand stronger {side} signals.",
                    "warning", impact=abs(d[side].net_profit),
                ))
                break

    # Auto vs manual
    if len(stats.by_source) == 2 and all(g.trades >= _MIN_GROUP for g in stats.by_source):
        s = {g.label: g for g in stats.by_source}
        a, m = s["Auto"], s["Manual"]
        better, worse = (a, m) if a.net_profit >= m.net_profit else (m, a)
        out.append(Insight(
            f"{better.label} is outperforming {worse.label}",
            f"Auto: net ${a.net_profit:,.0f} (PF {_fmt_pf(a.profit_factor)}); "
            f"Manual: net ${m.net_profit:,.0f} (PF {_fmt_pf(m.profit_factor)}).",
            f"Lean into {better.label.lower()} trading and review what {worse.label.lower()} is doing differently.",
            "info", impact=abs(better.net_profit - worse.net_profit),
        ))

    # Holding losers too long
    if (stats.losses >= _MIN_GROUP and stats.avg_hold_win_secs > 0
            and stats.avg_hold_loss_secs > 1.5 * stats.avg_hold_win_secs):
        out.append(Insight(
            "You hold losers longer than winners",
            f"Winners held ~{_fmt_dur(stats.avg_hold_win_secs)}, losers ~{_fmt_dur(stats.avg_hold_loss_secs)}.",
            "Honor your stop and set a max holding time — hoping a loser back to break-even is the costliest habit.",
            "warning", impact=stats.avg_loss * stats.losses,
        ))

    # Tail risk
    if stats.avg_loss > 0 and abs(stats.largest_loss) > 4 * stats.avg_loss and stats.losses >= 5:
        out.append(Insight(
            "One outsized loss",
            f"Largest loss ${stats.largest_loss:,.0f} is {abs(stats.largest_loss) / stats.avg_loss:.1f}× your average loss.",
            "Set a hard per-trade max loss; a single trade should never undo many wins.",
            "warning", impact=abs(stats.largest_loss),
        ))

    # Losing streak
    if stats.max_consec_losses >= 5:
        out.append(Insight(
            "Long losing streaks",
            f"Up to {stats.max_consec_losses} losses in a row; max drawdown ${stats.max_drawdown:,.0f}.",
            "Add a daily loss limit and a cool-down after consecutive losses to curb tilt.",
            "warning", impact=stats.max_drawdown,
        ))

    # Worst weekday
    wd_losers = [g for g in stats.by_weekday if g.trades >= _MIN_BUCKET and g.net_profit < 0]
    if wd_losers:
        g = min(wd_losers, key=lambda x: x.net_profit)
        out.append(Insight(
            f"{g.label} is consistently weak (UTC)",
            f"{g.label}: net ${g.net_profit:,.0f} over {g.trades} trades.",
            f"Investigate why — consider skipping or reducing size on {g.label}s. Treat as a hypothesis, not a rule.",
            "info", impact=abs(g.net_profit),
        ))

    severity_rank = {"critical": 0, "warning": 1, "good": 2, "info": 3}
    out.sort(key=lambda i: (severity_rank.get(i.severity, 9), -i.impact))
    return out[:8]


# ----------------------------------------------------------------------
# Formatting helpers (shared with the UI)
# ----------------------------------------------------------------------

def _fmt_pf(pf: float) -> str:
    if math.isinf(pf):
        return "∞"     # ∞
    return f"{pf:.2f}"


def _fmt_dur(seconds: float) -> str:
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s / 3600:.1f}h"
    return f"{s / 86400:.1f}d"
