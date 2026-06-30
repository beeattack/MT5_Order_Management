from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPainterPath

from core import analytics
from core.analytics import PerformanceStats, Insight

COLORS = {
    "bg":        "#1a1a2e",
    "panel":     "#16213e",
    "accent":    "#0f3460",
    "amber":     "#e8a838",
    "green":     "#00b894",
    "red":       "#e17055",
    "text":      "#eaeaea",
    "subtext":   "#a0a0b0",
    "btn":       "#0f3460",
    "btn_hover": "#1a4a8a",
    "row_alt":   "#1e2a4a",
}

_SEVERITY_COLOR = {
    "critical": COLORS["red"],
    "warning":  COLORS["amber"],
    "good":     COLORS["green"],
    "info":     COLORS["subtext"],
}

_PANEL_QSS = f"""
QWidget {{ background-color: {COLORS['bg']}; color: {COLORS['text']}; }}
QScrollArea {{ border: none; }}
QLabel#sectionTitle {{ font-size: 13px; font-weight: bold; padding: 8px 2px 2px 2px; }}
QLabel#cardKey {{ color: {COLORS['subtext']}; font-size: 11px; }}
QLabel#cardValue {{ font-size: 18px; font-weight: bold; font-family: "Consolas", monospace; }}
QFrame#card {{ background-color: {COLORS['panel']}; border: 1px solid {COLORS['accent']}; border-radius: 6px; }}
QFrame#insight {{ background-color: {COLORS['panel']}; border-radius: 6px; }}
QPushButton#chip {{
    background-color: {COLORS['panel']}; color: {COLORS['subtext']};
    border: 1px solid {COLORS['accent']}; border-radius: 12px;
    padding: 4px 14px; font-size: 11px; font-weight: bold;
}}
QPushButton#chip:hover {{ background-color: {COLORS['btn_hover']}; color: {COLORS['text']}; }}
QPushButton#chip:checked {{ background-color: {COLORS['accent']}; color: {COLORS['text']}; }}
QTableWidget {{
    background-color: {COLORS['panel']}; alternate-background-color: {COLORS['row_alt']};
    color: {COLORS['text']}; gridline-color: {COLORS['accent']};
    border: 1px solid {COLORS['accent']}; font-size: 11px;
}}
QHeaderView::section {{
    background-color: {COLORS['accent']}; color: {COLORS['text']};
    font-weight: bold; border: none; padding: 3px 6px; font-size: 11px;
}}
QScrollBar:vertical {{ background: {COLORS['panel']}; width: 10px; border: none; }}
QScrollBar::handle:vertical {{ background: {COLORS['accent']}; border-radius: 5px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


class EquityCurveWidget(QWidget):
    """Closed-trade cumulative P&L, drawn with QPainter (no chart library)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._curve: list[float] = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_curve(self, curve: list[float]) -> None:
        self._curve = list(curve)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(COLORS["panel"]))
        p.setPen(QPen(QColor(COLORS["accent"]), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        if len(self._curve) < 2:
            p.setPen(QColor(COLORS["subtext"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Not enough trades to plot")
            return

        pad_l, pad_r, pad_t, pad_b = 56, 14, 14, 22
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        ys = self._curve + [0.0]
        lo, hi = min(ys), max(ys)
        if hi == lo:
            hi += 1.0
            lo -= 1.0
        span = hi - lo

        def x_at(i: int) -> float:
            return pad_l + plot_w * i / (len(self._curve) - 1)

        def y_at(v: float) -> float:
            return pad_t + plot_h * (1 - (v - lo) / span)

        # zero baseline
        if lo <= 0 <= hi:
            yz = y_at(0.0)
            pen = QPen(QColor(COLORS["subtext"]), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(int(pad_l), int(yz), int(w - pad_r), int(yz))

        # axis labels (top, zero, bottom)
        p.setPen(QColor(COLORS["subtext"]))
        p.setFont(QFont("Consolas", 8))
        p.drawText(QRectF(2, y_at(hi) - 7, pad_l - 6, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{hi:,.0f}")
        p.drawText(QRectF(2, y_at(lo) - 7, pad_l - 6, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{lo:,.0f}")

        # build path
        path = QPainterPath()
        path.moveTo(QPointF(x_at(0), y_at(self._curve[0])))
        for i, v in enumerate(self._curve[1:], start=1):
            path.lineTo(QPointF(x_at(i), y_at(v)))

        ends_positive = self._curve[-1] >= 0
        line_color = QColor(COLORS["green"] if ends_positive else COLORS["red"])

        # subtle fill to the zero baseline
        fill = QPainterPath(path)
        base_y = y_at(0.0) if lo <= 0 <= hi else y_at(lo)
        fill.lineTo(QPointF(x_at(len(self._curve) - 1), base_y))
        fill.lineTo(QPointF(x_at(0), base_y))
        fill.closeSubpath()
        fc = QColor(line_color)
        fc.setAlpha(40)
        p.fillPath(fill, QBrush(fc))

        p.setPen(QPen(line_color, 2))
        p.drawPath(path)


class DonutChartWidget(QWidget):
    """Win/loss donut drawn with QPainter; win rate shown large in the center."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wins = 0
        self._losses = 0
        self._breakeven = 0.0
        self.setMinimumSize(200, 152)

    def set_data(self, wins: int, losses: int, breakeven: float = 0.0) -> None:
        self._wins, self._losses, self._breakeven = wins, losses, breakeven
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(COLORS["panel"]))
        p.setPen(QPen(QColor(COLORS["accent"]), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        thickness = 18
        diam = max(40, min(w, h) - 38)
        rx = (w - diam) / 2
        ry = (h - diam) / 2 - 6
        ring = QRectF(rx, ry, diam, diam)
        total = self._wins + self._losses

        # background ring
        p.setPen(QPen(QColor(COLORS["accent"]), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(ring, 0, 360 * 16)

        if total == 0:
            p.setPen(QColor(COLORS["subtext"]))
            p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            p.drawText(ring, Qt.AlignmentFlag.AlignCenter, "—")
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(0, ry + diam + 4, w, 16), Qt.AlignmentFlag.AlignHCenter, "No trades")
            return

        wr = self._wins / total * 100.0
        wins_span = int(round(360 * self._wins / total))
        start = 90 * 16  # top, going clockwise (negative span)
        p.setPen(QPen(QColor(COLORS["green"]), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(ring, start, -wins_span * 16)
        p.setPen(QPen(QColor(COLORS["red"]), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(ring, start - wins_span * 16, -(360 - wins_span) * 16)

        # center: big win rate %, colored vs the breakeven win rate (the target)
        meets = wr >= self._breakeven
        p.setPen(QColor(COLORS["green"] if meets else COLORS["red"]))
        p.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        p.drawText(QRectF(rx, ry + diam / 2 - 28, diam, 34),
                   Qt.AlignmentFlag.AlignCenter, f"{wr:.0f}%")
        p.setPen(QColor(COLORS["subtext"]))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRectF(rx, ry + diam / 2 + 4, diam, 16),
                   Qt.AlignmentFlag.AlignCenter, "WIN RATE")

        # legend + breakeven target under the ring
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor(COLORS["subtext"]))
        p.drawText(QRectF(0, ry + diam + 4, w, 16), Qt.AlignmentFlag.AlignHCenter,
                   f"{self._wins}W · {self._losses}L  ·  target ≥ {self._breakeven:.0f}%")


class DashboardPanel(QWidget):
    period_changed = Signal(object, object)   # (from_dt, to_dt) UTC-aware

    _PERIODS = ["Today", "1W", "1M", "3M", "YTD", "All"]

    _HERO_KEYS = frozenset({"Net P/L", "Profit Factor", "Expectancy"})

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._cards: dict[str, QLabel] = {}
        self._targets: dict[str, QLabel] = {}
        self._period = "1M"
        self._balance = 0.0
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- top bar: account snapshot + period chips ---
        top = QHBoxLayout()
        top.setContentsMargins(10, 6, 10, 4)
        top.setSpacing(14)

        self._snapshot = QLabel("Connect to view performance")
        self._snapshot.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; font-weight: bold; font-family: Consolas, monospace;"
        )
        top.addWidget(self._snapshot)
        top.addStretch()

        period_lbl = QLabel("Period:")
        period_lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 11px;")
        top.addWidget(period_lbl)
        self._chip_btns: dict[str, QPushButton] = {}
        for name in self._PERIODS:
            b = QPushButton(name)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(name == self._period)
            b.clicked.connect(lambda _=False, n=name: self._on_chip(n))
            self._chip_btns[name] = b
            top.addWidget(b)
        outer.addLayout(top)

        # --- scrollable content ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        col = QVBoxLayout(content)
        col.setContentsMargins(10, 4, 10, 10)
        col.setSpacing(6)

        # hero row: win-rate donut + the three headline metrics
        hero = QHBoxLayout()
        hero.setSpacing(8)
        self._donut = DonutChartWidget()
        hero.addWidget(self._donut, 0)
        for key in ("Net P/L", "Profit Factor", "Expectancy"):
            hero.addWidget(self._make_card(key, hero=True), 1)
        col.addLayout(hero)

        # secondary stat cards
        self._cards_grid = QGridLayout()
        self._cards_grid.setHorizontalSpacing(8)
        self._cards_grid.setVerticalSpacing(8)
        card_specs = [
            "Trades", "Avg Win / Loss", "Max Drawdown", "Recovery Factor",
            "Largest Win", "Largest Loss", "Max Loss Streak", "Avg Hold",
        ]
        for idx, key in enumerate(card_specs):
            row, c = divmod(idx, 4)
            self._cards_grid.addWidget(self._make_card(key), row, c)
        col.addLayout(self._cards_grid)

        # equity curve
        col.addWidget(self._section("Equity Curve  (cumulative closed-trade P/L)"))
        self._equity = EquityCurveWidget()
        col.addWidget(self._equity)

        # breakdowns
        col.addWidget(self._section("Breakdown"))
        bd_row = QHBoxLayout()
        bd_row.setSpacing(8)
        self._tbl_symbol = self._make_breakdown_table("Symbol")
        self._tbl_direction = self._make_breakdown_table("Direction")
        self._tbl_source = self._make_breakdown_table("Source")
        for t in (self._tbl_symbol, self._tbl_direction, self._tbl_source):
            bd_row.addWidget(t)
        col.addLayout(bd_row)

        # insights
        col.addWidget(self._section("Insights  ·  coaching from your own history"))
        self._insights_box = QVBoxLayout()
        self._insights_box.setSpacing(6)
        insights_holder = QWidget()
        insights_holder.setLayout(self._insights_box)
        col.addWidget(insights_holder)
        col.addStretch()

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _make_card(self, key: str, hero: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(100 if hero else 64)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        k = QLabel(key)
        k.setObjectName("cardKey")
        v = QLabel("—")
        v.setObjectName("cardValue")
        if hero:
            v.setStyleSheet(
                f"font-size: 30px; font-weight: bold; font-family: Consolas, monospace; color: {COLORS['subtext']};"
            )
        target = QLabel("")
        target.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 9px; background: transparent;")
        lay.addWidget(k)
        if hero:
            lay.addStretch()
        lay.addWidget(v)
        lay.addWidget(target)
        self._cards[key] = v
        self._targets[key] = target
        return card

    def _make_breakdown_table(self, first_col: str) -> QTableWidget:
        cols = [first_col, "Trades", "Win%", "Net P/L", "PF"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(24)
        t.setFont(QFont("Consolas", 10))
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(cols)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        t.setMinimumHeight(120)
        return t

    # ------------------------------------------------------------------
    # Period selection
    # ------------------------------------------------------------------

    def _on_chip(self, name: str) -> None:
        self._period = name
        for n, b in self._chip_btns.items():
            b.setChecked(n == name)
        self.period_changed.emit(*self.current_range())

    def current_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        if self._period == "Today":
            frm = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._period == "1W":
            frm = now - timedelta(days=7)
        elif self._period == "1M":
            frm = now - timedelta(days=30)
        elif self._period == "3M":
            frm = now - timedelta(days=90)
        elif self._period == "YTD":
            frm = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        else:  # All
            frm = datetime(2000, 1, 1, tzinfo=timezone.utc)
        return frm, now

    # ------------------------------------------------------------------
    # Public update API
    # ------------------------------------------------------------------

    def update_account(self, balance: float, equity: float, floating: float, open_count: int) -> None:
        self._balance = balance
        sign = "+" if floating >= 0 else ""
        self._snapshot.setText(
            f"Balance ${balance:,.2f}    Equity ${equity:,.2f}    "
            f"Floating {sign}${floating:,.2f}    Open {open_count}"
        )

    def clear(self) -> None:
        self._balance = 0.0
        self._snapshot.setText("Connect to view performance")
        for key, v in self._cards.items():
            v.setText("—")
            v.setStyleSheet(
                f"color: {COLORS['subtext']}; font-size: {self._value_font_size(key)}px; "
                f"font-weight: bold; font-family: Consolas, monospace;"
            )
        for t_lbl in self._targets.values():
            t_lbl.setText("")
        self._donut.set_data(0, 0, 0.0)
        self._equity.set_curve([])
        for t in (self._tbl_symbol, self._tbl_direction, self._tbl_source):
            t.setRowCount(0)
        self._clear_insights()

    def update_dashboard(self, stats: PerformanceStats, insights: list[Insight]) -> None:
        self._donut.set_data(stats.wins, stats.losses, stats.breakeven_win_rate)
        self._set_money_card("Net P/L", stats.net_profit)
        self._set_card("Profit Factor", analytics._fmt_pf(stats.profit_factor))
        self._set_money_card("Expectancy", stats.expectancy, suffix=" /trade")
        self._set_card("Trades", f"{stats.total_trades}  ({stats.wins}W/{stats.losses}L)")
        self._set_targets(stats)
        if self._period == "Today":
            self._set_daily_growth(stats.net_profit)
        payoff = "∞" if stats.payoff_ratio == float("inf") else f"{stats.payoff_ratio:.2f}"
        self._set_card("Avg Win / Loss", f"${stats.avg_win:,.0f} / ${stats.avg_loss:,.0f}  ({payoff})")
        self._set_money_card("Max Drawdown", -stats.max_drawdown)
        self._set_card("Recovery Factor", analytics._fmt_pf(stats.recovery_factor))
        self._set_money_card("Largest Win", stats.largest_win)
        self._set_money_card("Largest Loss", stats.largest_loss)
        self._set_card("Max Loss Streak", str(stats.max_consec_losses))
        self._set_card("Avg Hold", analytics._fmt_dur(stats.avg_hold_secs) if stats.total_trades else "—")

        self._equity.set_curve(stats.equity_curve)

        self._fill_breakdown(self._tbl_symbol, stats.by_symbol)
        self._fill_breakdown(self._tbl_direction, stats.by_direction)
        self._fill_breakdown(self._tbl_source, stats.by_source)

        self._render_insights(insights)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    _STATUS_COLOR = {
        "good": COLORS["green"], "warn": COLORS["amber"],
        "bad": COLORS["red"], "neutral": COLORS["subtext"],
    }

    def _value_font_size(self, key: str) -> int:
        return 30 if key in self._HERO_KEYS else 18

    def _set_target(self, key: str, text: str, status: str = "neutral") -> None:
        lbl = self._targets[key]
        lbl.setText("target: " + text if status != "neutral" else text)
        lbl.setStyleSheet(
            f"color: {self._STATUS_COLOR[status]}; font-size: 9px; font-weight: bold; background: transparent;"
        )

    def _set_targets(self, stats: PerformanceStats) -> None:
        has = stats.total_trades > 0

        def hi(v, good, warn):   # higher is better
            return "good" if v >= good else ("warn" if v >= warn else "bad")

        def lo(v, good, warn):   # lower is better
            return "good" if v <= good else ("warn" if v <= warn else "bad")

        def st(status):          # suppress judgment when there's no data
            return status if has else "neutral"

        self._set_target("Net P/L", "> 0", st("good" if stats.net_profit > 0 else "bad"))
        self._set_target("Profit Factor", "≥ 1.5", st(hi(stats.profit_factor, 1.5, 1.0)))
        self._set_target("Expectancy", "> 0 / trade", st("good" if stats.expectancy > 0 else "bad"))
        self._set_target("Trades", "≥ 30 for confidence", st(hi(stats.total_trades, 30, 10)))
        self._set_target("Avg Win / Loss", "payoff ≥ 1.5", st(hi(stats.payoff_ratio, 1.5, 1.0)))
        self._set_target("Max Drawdown", "lower is better", "neutral")
        self._set_target("Recovery Factor", "≥ 3", st(hi(stats.recovery_factor, 3.0, 1.0)))
        self._set_target("Largest Win", "higher is better", "neutral")
        if has and stats.avg_loss > 0:
            ratio = abs(stats.largest_loss) / stats.avg_loss
            ll = "good" if ratio <= 3 else ("warn" if ratio <= 5 else "bad")
        else:
            ll = "neutral"
        self._set_target("Largest Loss", "≤ 3× avg loss", ll)
        self._set_target("Max Loss Streak", "≤ 4 ideal", st(lo(stats.max_consec_losses, 4, 6)))
        self._set_target("Avg Hold", "—", "neutral")

    def _set_daily_growth(self, net_profit: float) -> None:
        """On the Today view, show today's profit as a % of the start-of-day
        balance (i.e. the previous day's closing balance) on the Net P/L card."""
        prev_balance = self._balance - net_profit
        lbl = self._targets["Net P/L"]
        if prev_balance <= 0:
            return
        pct = net_profit / prev_balance * 100.0
        sign = "+" if pct >= 0 else ""
        status = "good" if net_profit > 0 else ("bad" if net_profit < 0 else "neutral")
        lbl.setText(f"{sign}{pct:.2f}% of prev-day balance")
        lbl.setStyleSheet(
            f"color: {self._STATUS_COLOR[status]}; font-size: 9px; "
            f"font-weight: bold; background: transparent;"
        )

    def _set_card(self, key: str, text: str) -> None:
        lbl = self._cards[key]
        lbl.setText(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {self._value_font_size(key)}px; "
            f"font-weight: bold; font-family: Consolas, monospace;"
        )

    def _set_money_card(self, key: str, value: float, suffix: str = "") -> None:
        lbl = self._cards[key]
        sign = "+" if value >= 0 else ""
        arrow = " ▲" if value > 0 else (" ▼" if value < 0 else "")
        color = COLORS["green"] if value >= 0 else COLORS["red"]
        lbl.setText(f"{sign}${value:,.2f}{suffix}{arrow}")
        lbl.setStyleSheet(
            f"color: {color}; font-size: {self._value_font_size(key)}px; "
            f"font-weight: bold; font-family: Consolas, monospace;"
        )

    def _fill_breakdown(self, table: QTableWidget, groups) -> None:
        table.setRowCount(len(groups))
        for row, g in enumerate(groups):
            cells = [
                g.label,
                str(g.trades),
                f"{g.win_rate:.0f}%",
                f"{'+' if g.net_profit >= 0 else ''}{g.net_profit:,.0f}",
                analytics._fmt_pf(g.profit_factor),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if c >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 3:
                    item.setForeground(QColor(COLORS["green"] if g.net_profit >= 0 else COLORS["red"]))
                table.setItem(row, c, item)

    def _clear_insights(self) -> None:
        while self._insights_box.count():
            item = self._insights_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_insights(self, insights: list[Insight]) -> None:
        self._clear_insights()
        for idx, ins in enumerate(insights):
            self._insights_box.addWidget(self._make_insight_card(ins, hero=(idx == 0)))

    def _make_insight_card(self, ins: Insight, hero: bool) -> QFrame:
        color = _SEVERITY_COLOR.get(ins.severity, COLORS["subtext"])
        bg = COLORS["row_alt"] if hero else COLORS["panel"]
        border = 6 if hero else 4
        card = QFrame()
        card.setObjectName("insight")
        card.setStyleSheet(
            f"QFrame#insight {{ background-color: {bg}; border-radius: 6px; "
            f"border-left: {border}px solid {color}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 9 if hero else 7, 14, 9 if hero else 7)
        lay.setSpacing(3 if hero else 2)

        if hero:
            tag = QLabel("★  KEY TAKEAWAY")
            tag.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold; letter-spacing: 1px; background: transparent;"
            )
            lay.addWidget(tag)

        title = QLabel(ins.title)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {color}; font-size: {15 if hero else 12}px; font-weight: bold; background: transparent;"
        )
        lay.addWidget(title)

        finding = QLabel(ins.finding)
        finding.setWordWrap(True)
        finding.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {12 if hero else 11}px; background: transparent;"
        )
        lay.addWidget(finding)

        suggestion = QLabel("→ " + ins.suggestion)
        suggestion.setWordWrap(True)
        suggestion.setStyleSheet(
            f"color: {COLORS['subtext']}; font-size: {12 if hero else 11}px; background: transparent;"
        )
        lay.addWidget(suggestion)
        return card
