from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSizeGrip,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap, QPainter, QPen

from models.order import Order

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
}

_ROW_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

# Transparency slider range (window opacity %)
MIN_OPACITY_PCT = 30
DEFAULT_OPACITY_PCT = 92


def _blank_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _make_x_icon(size: int = 14, color: str = "#ffffff") -> QIcon:
    """A crisp X drawn with QPainter (reliable at small sizes, unlike a glyph)."""
    pm = _blank_pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 2))
    m = 4
    p.drawLine(m, m, size - m, size - m)
    p.drawLine(size - m, m, m, size - m)
    p.end()
    return QIcon(pm)


def _make_compact_icon(size: int = 14, color: str = "#eaeaea") -> QIcon:
    """Stacked rows — represents the compact orders view."""
    pm = _blank_pixmap(size)
    p = QPainter(pm)
    p.setPen(QPen(QColor(color), 1.6))
    for y in (4, 7, 10):
        p.drawLine(3, y, size - 3, y)
    p.end()
    return QIcon(pm)


def _make_normal_icon(size: int = 14, color: str = "#eaeaea") -> QIcon:
    """A framed window — represents the full normal window."""
    pm = _blank_pixmap(size)
    p = QPainter(pm)
    p.setPen(QPen(QColor(color), 1.4))
    p.drawRect(3, 3, size - 7, size - 7)
    p.drawLine(3, 6, size - 4, 6)   # title bar
    p.end()
    return QIcon(pm)

_PANEL_QSS = f"""
QWidget#GhostPanel {{ background-color: {COLORS['bg']}; border: 1px solid {COLORS['accent']}; }}
QLabel#ghostTotalKey {{ color: {COLORS['subtext']}; font-size: 10px; font-weight: bold; }}
QLabel#ghostTotal    {{ font-size: 14px; font-weight: bold; font-family: Consolas, monospace; }}
QLabel#ghostHint {{ color: {COLORS['subtext']}; font-size: 10px; }}
QPushButton#modeBtn {{
    background-color: {COLORS['btn']}; color: {COLORS['text']}; border: none;
    border-radius: 3px; padding: 3px 9px; font-size: 10px; font-weight: bold;
}}
QPushButton#modeBtn:hover {{ background-color: {COLORS['btn_hover']}; }}
QPushButton#modeBtn:checked {{ background-color: {COLORS['btn_hover']}; }}
QComboBox#ghostSymbol {{
    background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']}; border-radius: 3px;
    padding: 1px 5px; font-size: 10px;
}}
QComboBox#ghostSymbol::drop-down {{
    border: none; background-color: {COLORS['accent']}; width: 14px;
    border-top-right-radius: 3px; border-bottom-right-radius: 3px;
}}
QComboBox#ghostSymbol QAbstractItemView {{
    background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    selection-background-color: {COLORS['accent']};
}}
QTableWidget {{ selection-background-color: {COLORS['btn_hover']}; outline: none; }}
QTableWidget::item:selected {{ background-color: {COLORS['btn_hover']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {COLORS['accent']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {COLORS['btn_hover']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 11px; background: {COLORS['amber']}; border-radius: 5px; margin: -5px 0;
}}
QTableWidget {{
    background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']}; gridline-color: {COLORS['accent']};
}}
QScrollBar:vertical {{ background: {COLORS['panel']}; width: 8px; border: none; }}
QScrollBar::handle:vertical {{ background: {COLORS['accent']}; border-radius: 4px; min-height: 18px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


class MiniChart(QWidget):
    """Compact candlestick chart for the ghost overlay.

    Paints whatever bars it is given — an MT5 rates array or any sequence of
    (time, open, high, low, close) — scaled to the widget. Deliberately plain:
    at ~290px wide there is room for candles and a last-price tag, nothing more.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars = []
        self._symbol = ""
        self._digits = 5
        self.setMinimumHeight(120)

    def set_bars(self, bars, symbol: str = "", digits: int = 5) -> None:
        self._bars = [] if bars is None else list(bars)
        self._symbol = symbol
        self._digits = digits
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(COLORS["panel"]))

        if len(self._bars) < 2:
            p.setPen(QColor(COLORS["subtext"]))
            p.setFont(QFont("Segoe UI", 8))
            msg = "No chart data" if self._symbol else "Pick a symbol"
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)
            return

        pad_r = 48          # room for the price tag
        pad_v = 6
        plot_w = max(1, w - pad_r - 4)
        plot_h = max(1, h - 2 * pad_v)

        highs = [float(b["high"]) for b in self._bars]
        lows = [float(b["low"]) for b in self._bars]
        hi, lo = max(highs), min(lows)
        span = (hi - lo) or 1e-9

        def y(v: float) -> float:
            return pad_v + plot_h * (1 - (v - lo) / span)

        n = len(self._bars)
        step = plot_w / n
        body_w = max(1.0, min(6.0, step * 0.66))

        for i, bar in enumerate(self._bars):
            o, c = float(bar["open"]), float(bar["close"])
            up = c >= o
            color = QColor(COLORS["green"] if up else COLORS["red"])
            cx = 4 + step * (i + 0.5)

            p.setPen(QPen(color, 1))
            p.drawLine(int(cx), int(y(float(bar["high"]))),
                       int(cx), int(y(float(bar["low"]))))

            top, bot = y(max(o, c)), y(min(o, c))
            rect = QRectF(cx - body_w / 2, top, body_w, max(1.0, bot - top))
            p.fillRect(rect, color)

        # last price: dashed level plus a tag in the right margin
        last = float(self._bars[-1]["close"])
        first_open = float(self._bars[0]["open"])
        tag_color = QColor(COLORS["green"] if last >= first_open else COLORS["red"])
        ly = y(last)
        pen = QPen(tag_color, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(4, int(ly), w - pad_r, int(ly))

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(tag_color)
        p.drawText(QRectF(w - pad_r + 2, ly - 8, pad_r - 4, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{last:,.{self._digits}f}")

        # high / low of the window, top-right and bottom-right
        p.setFont(QFont("Consolas", 7))
        p.setPen(QColor(COLORS["subtext"]))
        p.drawText(QRectF(w - pad_r + 2, pad_v - 3, pad_r - 4, 12),
                   Qt.AlignmentFlag.AlignLeft, f"{hi:,.{self._digits}f}")
        p.drawText(QRectF(w - pad_r + 2, h - pad_v - 9, pad_r - 4, 12),
                   Qt.AlignmentFlag.AlignLeft, f"{lo:,.{self._digits}f}")


class GhostPanel(QWidget):
    """Minimal always-on-top overlay: active orders with P/L and a close button,
    plus quick switches back to Compact / Normal mode."""

    switch_normal        = Signal()
    switch_compact       = Signal()
    close_order_requested = Signal(object)   # ticket (closes 100%); object avoids
    #                                          Qt's 32-bit int limit for large MT5 tickets
    opacity_changed      = Signal(float)  # window opacity 0.30–1.00
    chart_toggled        = Signal(bool)   # expandable M15 chart shown/hidden
    chart_symbol_changed = Signal(str)

    CONTENT_WIDTH = 300
    # Height the overlay grows by when the chart area opens
    CHART_AREA_HEIGHT = 186

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GhostPanel")
        self.setStyleSheet(_PANEL_QSS)
        self._x_icon = _make_x_icon()
        self._drag_pos = None
        self._tickets: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(6)

        key = QLabel("P/L")
        key.setObjectName("ghostTotalKey")
        header.addWidget(key)
        self._total = QLabel("—")
        self._total.setObjectName("ghostTotal")
        header.addWidget(self._total)
        header.addStretch()

        compact_btn = QPushButton()
        compact_btn.setObjectName("modeBtn")
        compact_btn.setIcon(_make_compact_icon())
        compact_btn.setIconSize(QSize(14, 14))
        compact_btn.setFixedSize(26, 22)
        compact_btn.setToolTip("Compact mode")
        compact_btn.clicked.connect(self.switch_compact)
        header.addWidget(compact_btn)

        normal_btn = QPushButton()
        normal_btn.setObjectName("modeBtn")
        normal_btn.setIcon(_make_normal_icon())
        normal_btn.setIconSize(QSize(14, 14))
        normal_btn.setFixedSize(26, 22)
        normal_btn.setToolTip("Normal mode")
        normal_btn.clicked.connect(self.switch_normal)
        header.addWidget(normal_btn)

        layout.addLayout(header)

        # Balance / Equity line
        acct = QHBoxLayout()
        acct.setSpacing(12)
        self._bal_lbl = QLabel("Bal —")
        self._bal_lbl.setObjectName("ghostHint")
        self._eq_lbl = QLabel("Eq —")
        self._eq_lbl.setObjectName("ghostHint")
        acct.addWidget(self._bal_lbl)
        acct.addWidget(self._eq_lbl)
        acct.addStretch()
        layout.addLayout(acct)

        # Transparency slider row
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(6)
        hint = QLabel("◐ Opacity")
        hint.setObjectName("ghostHint")
        opacity_row.addWidget(hint)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(MIN_OPACITY_PCT, 100)
        self._opacity_slider.setValue(DEFAULT_OPACITY_PCT)
        self._opacity_slider.valueChanged.connect(self._on_opacity)
        opacity_row.addWidget(self._opacity_slider, 1)

        self._opacity_lbl = QLabel(f"{DEFAULT_OPACITY_PCT}%")
        self._opacity_lbl.setObjectName("ghostHint")
        self._opacity_lbl.setFixedWidth(34)
        self._opacity_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        opacity_row.addWidget(self._opacity_lbl)

        layout.addLayout(opacity_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Symbol", "Type", "Vol", "P/L", ""])
        self._table.horizontalHeader().setVisible(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # clicking an order charts its symbol (the close button is a cell
        # widget, so hitting ✕ never reaches this)
        self._table.cellClicked.connect(self._on_order_clicked)
        self._table.setFont(QFont("Consolas", 11))
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)   # Symbol
        for col in (1, 2, 3, 4):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 42)    # Type
        self._table.setColumnWidth(2, 48)    # Volume
        self._table.setColumnWidth(3, 74)    # P/L
        self._table.setColumnWidth(4, 28)    # close
        layout.addWidget(self._table)

        # --- expandable chart area (hidden until the button is pressed) ---
        self._chart_area = QWidget()
        self._chart_area.setFixedHeight(self.CHART_AREA_HEIGHT)
        area = QVBoxLayout(self._chart_area)
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(3)

        # symbol picker sits top-right of the area
        pick = QHBoxLayout()
        pick.setContentsMargins(0, 0, 0, 0)
        pick.setSpacing(4)
        pick.addStretch()
        self._symbol_combo = QComboBox()
        self._symbol_combo.setObjectName("ghostSymbol")
        self._symbol_combo.setFixedWidth(130)
        self._symbol_combo.setToolTip("Symbols in the MT5 Market Watch")
        self._symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        pick.addWidget(self._symbol_combo)
        area.addLayout(pick)

        self._chart = MiniChart()
        area.addWidget(self._chart, 1)

        self._chart_area.setVisible(False)
        layout.addWidget(self._chart_area)

        # --- bottom bar, pinned to the window's bottom border: the chart
        # toggle on the left, the resize grip in the corner. The chart area
        # opens above it, so the button never moves.
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)
        self._chart_btn = QPushButton("▸ M15 Chart")
        self._chart_btn.setObjectName("modeBtn")
        self._chart_btn.setCheckable(True)
        self._chart_btn.setFixedHeight(20)
        self._chart_btn.setToolTip("Show the M15 chart for a symbol")
        self._chart_btn.toggled.connect(self._on_chart_toggled)
        bottom.addWidget(self._chart_btn)
        bottom.addStretch()
        bottom.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(bottom)

    def _on_order_clicked(self, row: int, _col: int) -> None:
        """Chart the clicked order's symbol, opening the chart if it's closed."""
        item = self._table.item(row, 0)
        if item is None:
            return
        self.select_chart_symbol(item.text())
        if not self._chart_btn.isChecked():
            self._chart_btn.setChecked(True)   # emits chart_toggled -> window grows

    def _on_chart_toggled(self, shown: bool) -> None:
        self._chart_btn.setText(("▾ " if shown else "▸ ") + "M15 Chart")
        self._chart_area.setVisible(shown)
        self.chart_toggled.emit(shown)

    def _on_symbol_changed(self, symbol: str) -> None:
        self._sync_chart_row()
        if symbol:
            self.chart_symbol_changed.emit(symbol)

    def _sync_chart_row(self) -> None:
        """Highlight the order whose symbol is charted, if one is open.

        The highlight marks *what is charted*, not what was last touched:
        clicking ✕ would otherwise move it to a row whose symbol isn't on the
        chart, and a rebuild after an order closes would drop it entirely.
        """
        symbol = self.chart_symbol()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.text() == symbol:
                self._table.selectRow(row)
                return
        self._table.clearSelection()

    # ------------------------------------------------------------------
    # Chart API
    # ------------------------------------------------------------------

    def chart_visible(self) -> bool:
        return self._chart_btn.isChecked()

    def set_chart_visible(self, shown: bool) -> None:
        """Restore the saved expanded state without re-emitting the toggle."""
        self._chart_btn.blockSignals(True)
        self._chart_btn.setChecked(shown)
        self._chart_btn.blockSignals(False)
        self._chart_btn.setText(("▾ " if shown else "▸ ") + "M15 Chart")
        self._chart_area.setVisible(shown)

    def chart_symbol(self) -> str:
        return self._symbol_combo.currentText().strip()

    def set_symbol_choices(self, symbols: list[str]) -> None:
        """Fill the picker from the MT5 Market Watch, keeping the selection."""
        current = self.chart_symbol()
        self._symbol_combo.blockSignals(True)
        self._symbol_combo.clear()
        self._symbol_combo.addItems(symbols)
        idx = self._symbol_combo.findText(current)
        if idx < 0 and symbols:
            idx = 0
        self._symbol_combo.setCurrentIndex(idx)
        self._symbol_combo.blockSignals(False)
        if idx >= 0 and self._symbol_combo.currentText() != current:
            self.chart_symbol_changed.emit(self._symbol_combo.currentText())

    def select_chart_symbol(self, symbol: str) -> None:
        """Select *symbol* in the picker, adding it if the list lacks it.

        An open order's symbol is always chartable even when it isn't in the
        Market Watch snapshot the picker was filled from.
        """
        symbol = (symbol or "").strip()
        if not symbol:
            return
        idx = self._symbol_combo.findText(symbol)
        if idx < 0:
            self._symbol_combo.addItem(symbol)
            idx = self._symbol_combo.count() - 1
        self._symbol_combo.setCurrentIndex(idx)

    def set_chart_bars(self, bars, digits: int = 5) -> None:
        self._chart.set_bars(bars, self.chart_symbol(), digits)

    def _on_opacity(self, value: int) -> None:
        self._opacity_lbl.setText(f"{value}%")
        self.opacity_changed.emit(value / 100.0)

    def set_opacity_pct(self, pct: int) -> None:
        """Restore the saved opacity (updates slider, label and window)."""
        pct = max(MIN_OPACITY_PCT, min(100, int(pct)))
        self._opacity_slider.setValue(pct)

    # ------------------------------------------------------------------
    # Public update API
    # ------------------------------------------------------------------

    def update_orders(self, orders: list[Order]) -> None:
        new_tickets = [o.ticket for o in orders]
        if new_tickets == self._tickets:
            # Same orders — refresh only the live P/L; keep the close buttons
            # intact so a click isn't interrupted by the 100ms rebuild
            for row, order in enumerate(orders):
                self._set_pl(row, order.profit)
            self._sync_chart_row()
            return

        self._tickets = new_tickets
        self._table.setRowCount(0)
        self._table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            sym = QTableWidgetItem(order.symbol)
            sym.setFlags(_ROW_FLAGS)
            self._table.setItem(row, 0, sym)

            typ = QTableWidgetItem(order.order_type)
            typ.setFlags(_ROW_FLAGS)
            typ.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            typ.setForeground(QColor(COLORS["green"] if order.order_type == "BUY" else COLORS["red"]))
            self._table.setItem(row, 1, typ)

            vol = QTableWidgetItem(f"{order.volume:.2f}")
            vol.setFlags(_ROW_FLAGS)
            vol.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, vol)

            self._set_pl(row, order.profit)

            btn = QPushButton()
            btn.setIcon(self._x_icon)
            btn.setIconSize(QSize(11, 11))
            btn.setFixedSize(24, 20)
            btn.setToolTip(f"Close #{order.ticket} (100%)")
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {COLORS['red']}; border-radius: 3px; }}"
                f"QPushButton:hover {{ background-color: #c0392b; }}"
            )
            # pressing the button also moves the view's selection to its row;
            # put the highlight back on the charted symbol afterwards
            btn.clicked.connect(lambda _=False, t=order.ticket: (
                self.close_order_requested.emit(t), self._sync_chart_row()))
            self._table.setCellWidget(row, 4, btn)

        self._sync_chart_row()

    def _set_pl(self, row: int, profit: float) -> None:
        sign = "+" if profit >= 0 else ""
        item = QTableWidgetItem(f"{sign}{profit:,.2f}")
        item.setFlags(_ROW_FLAGS)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setForeground(QColor(COLORS["green"] if profit >= 0 else COLORS["red"]))
        self._table.setItem(row, 3, item)

    def update_account(self, balance: float, equity: float, profit: float) -> None:
        sign = "+" if profit >= 0 else ""
        color = COLORS["green"] if profit >= 0 else COLORS["red"]
        self._total.setText(f"{sign}${profit:,.2f}")
        self._total.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold; font-family: Consolas, monospace;"
        )
        self._bal_lbl.setText(f"Bal ${balance:,.2f}")
        self._eq_lbl.setText(f"Eq ${equity:,.2f}")

    # ------------------------------------------------------------------
    # Drag-to-move (frameless ghost window)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
