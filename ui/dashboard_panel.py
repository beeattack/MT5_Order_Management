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


class DashboardPanel(QWidget):
    period_changed = Signal(object, object)   # (from_dt, to_dt) UTC-aware

    _PERIODS = ["Today", "1W", "1M", "3M", "YTD", "All"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._cards: dict[str, QLabel] = {}
        self._period = "1M"
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

        # stat cards
        self._cards_grid = QGridLayout()
        self._cards_grid.setHorizontalSpacing(8)
        self._cards_grid.setVerticalSpacing(8)
        card_specs = [
            "Net P/L", "Profit Factor", "Win Rate", "Expectancy",
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

    def _make_card(self, key: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(58)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)
        k = QLabel(key)
        k.setObjectName("cardKey")
        v = QLabel("—")
        v.setObjectName("cardValue")
        lay.addWidget(k)
        lay.addWidget(v)
        self._cards[key] = v
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
        sign = "+" if floating >= 0 else ""
        self._snapshot.setText(
            f"Balance ${balance:,.2f}    Equity ${equity:,.2f}    "
            f"Floating {sign}${floating:,.2f}    Open {open_count}"
        )

    def clear(self) -> None:
        self._snapshot.setText("Connect to view performance")
        for v in self._cards.values():
            v.setText("—")
            v.setStyleSheet("font-size: 18px; font-weight: bold; font-family: Consolas, monospace;")
        self._equity.set_curve([])
        for t in (self._tbl_symbol, self._tbl_direction, self._tbl_source):
            t.setRowCount(0)
        self._clear_insights()

    def update_dashboard(self, stats: PerformanceStats, insights: list[Insight]) -> None:
        self._set_money_card("Net P/L", stats.net_profit)
        self._set_card("Profit Factor", analytics._fmt_pf(stats.profit_factor))
        self._set_card("Win Rate", f"{stats.win_rate:.1f}%")
        self._set_money_card("Expectancy", stats.expectancy, suffix=" /trade")
        self._set_card("Trades", f"{stats.total_trades}  ({stats.wins}W/{stats.losses}L)")
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

    def _set_card(self, key: str, text: str) -> None:
        lbl = self._cards[key]
        lbl.setText(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 18px; font-weight: bold; font-family: Consolas, monospace;"
        )

    def _set_money_card(self, key: str, value: float, suffix: str = "") -> None:
        lbl = self._cards[key]
        sign = "+" if value >= 0 else ""
        color = COLORS["green"] if value >= 0 else COLORS["red"]
        lbl.setText(f"{sign}${value:,.2f}{suffix}")
        lbl.setStyleSheet(
            f"color: {color}; font-size: 18px; font-weight: bold; font-family: Consolas, monospace;"
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
        for ins in insights:
            color = _SEVERITY_COLOR.get(ins.severity, COLORS["subtext"])
            card = QFrame()
            card.setObjectName("insight")
            card.setStyleSheet(
                f"QFrame#insight {{ background-color: {COLORS['panel']}; border-radius: 6px; "
                f"border-left: 4px solid {color}; }}"
            )
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 7, 12, 7)
            lay.setSpacing(2)

            title = QLabel(ins.title)
            title.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold; background: transparent;")
            lay.addWidget(title)

            finding = QLabel(ins.finding)
            finding.setWordWrap(True)
            finding.setStyleSheet(f"color: {COLORS['text']}; font-size: 11px; background: transparent;")
            lay.addWidget(finding)

            suggestion = QLabel("→ " + ins.suggestion)
            suggestion.setWordWrap(True)
            suggestion.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 11px; background: transparent;")
            lay.addWidget(suggestion)

            self._insights_box.addWidget(card)
