from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from models.order import Order
from utils.timezone_manager import format_dt, DEFAULT_TZ

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

_COLUMNS = ["Ticket", "Symbol", "Type", "Volume",
            "Open Price", "Current", "SL", "TP", "Profit", "Open Time", "Actions"]

# Columns hidden in compact mode (by index): Ticket, Open Price, Current, SL, TP, Open Time
_COMPACT_HIDDEN_COLS = frozenset({0, 4, 5, 6, 7, 9})

# Fixed widths used in compact mode for visible columns
_COMPACT_COL_WIDTHS = {
    "Symbol":  82,
    "Type":    56,
    "Volume":  68,
    "Profit":  95,
}

_PANEL_QSS = f"""
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
}}
QLabel#panelTitle {{
    color: {COLORS['text']};
    font-size: 14px;
    font-weight: bold;
    padding: 6px 0px 4px 4px;
}}
QTableWidget {{
    background-color: {COLORS['panel']};
    alternate-background-color: {COLORS['row_alt']};
    color: {COLORS['text']};
    gridline-color: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
    font-size: 12px;
    selection-background-color: {COLORS['accent']};
}}
QTableWidget::item {{
    padding: 2px 6px;
}}
QHeaderView::section {{
    background-color: {COLORS['accent']};
    color: {COLORS['text']};
    font-weight: bold;
    font-size: 12px;
    border: none;
    padding: 4px 6px;
}}
QScrollBar:vertical {{
    background: {COLORS['panel']};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['accent']};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QPushButton {{
    background-color: {COLORS['btn']};
    color: {COLORS['text']};
    border: none;
    border-radius: 3px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {COLORS['btn_hover']};
}}
"""


class OrdersPanel(QWidget):
    close_order_requested  = Signal(int, float)
    close_all_requested    = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._compact = False
        self._tz_name = DEFAULT_TZ
        self._last_orders: list[Order] = []
        self._build_ui()

    def set_timezone(self, tz_name: str) -> None:
        self._tz_name = tz_name
        self.update_orders(self._last_orders)

    def order_count(self) -> int:
        return len(self._last_orders)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # Header row widget — hidden in compact mode
        self._header_widget = QWidget()
        self._header_widget.setStyleSheet("background: transparent;")
        header_row = QHBoxLayout(self._header_widget)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._title_label = QLabel("Active Orders")
        self._title_label.setObjectName("panelTitle")
        header_row.addWidget(self._title_label)

        # Compact-mode equity / P/L labels (hidden in normal mode)
        self._compact_equity_lbl = QLabel("EQUITY  —")
        self._compact_equity_lbl.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; font-weight: bold;"
            f" font-family: Consolas, monospace; padding: 0 6px;"
        )
        self._compact_equity_lbl.setVisible(False)
        header_row.addWidget(self._compact_equity_lbl)

        self._compact_pl_lbl = QLabel("P/L  —")
        self._compact_pl_lbl.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; font-weight: bold;"
            f" font-family: Consolas, monospace; padding: 0 6px;"
        )
        self._compact_pl_lbl.setVisible(False)
        header_row.addWidget(self._compact_pl_lbl)

        header_row.addStretch()

        self._close_all_btn = QPushButton("⬛  Close All Orders")
        self._close_all_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['red']}; color: #ffffff; "
            f"border-radius: 4px; padding: 4px 16px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #c0392b; }}"
            f"QPushButton:disabled {{ background-color: {COLORS['accent']}; color: {COLORS['subtext']}; }}"
        )
        self._close_all_btn.setEnabled(False)
        self._close_all_btn.clicked.connect(self.close_all_requested)
        header_row.addWidget(self._close_all_btn)

        layout.addWidget(self._header_widget)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setShowGrid(True)

        # Column sizing — all data columns auto-fit content, Actions stretches
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(50)
        for col_idx, col_name in enumerate(_COLUMNS):
            if col_name != "Actions":
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.ResizeToContents)

        # Monospace font for number columns
        mono = QFont("Consolas", 11)
        self._table.setFont(mono)

        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Public update method
    # ------------------------------------------------------------------

    def update_orders(self, orders: list[Order]) -> None:
        self._last_orders = orders

        new_tickets = [str(o.ticket) for o in orders]
        current_tickets = [
            self._table.item(r, 0).text() if self._table.item(r, 0) else ""
            for r in range(self._table.rowCount())
        ]

        if new_tickets == current_tickets:
            # Same order list — update only the live columns; leave action widgets intact
            for row, order in enumerate(orders):
                self._set_item(row, 5, f"{order.current_price:,.{order.digits}f}")
                profit_sign = "+" if order.profit >= 0 else ""
                profit_item = QTableWidgetItem(f"{profit_sign}{order.profit:,.2f}")
                profit_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                profit_item.setForeground(
                    QColor(COLORS["green"] if order.profit >= 0 else COLORS["red"])
                )
                self._table.setItem(row, 8, profit_item)
            self._close_all_btn.setEnabled(bool(orders))
            return

        # Structural change (orders added/removed/reordered) — full rebuild
        self._table.setRowCount(0)
        self._table.setRowCount(len(orders))

        for row, order in enumerate(orders):
            self._set_item(row, 0, str(order.ticket))
            self._set_item(row, 1, order.symbol)

            type_item = QTableWidgetItem(order.order_type)
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            type_color = QColor(COLORS["green"]) if order.order_type == "BUY" else QColor(COLORS["red"])
            type_item.setForeground(type_color)
            self._table.setItem(row, 2, type_item)

            d = order.digits
            self._set_item(row, 3, f"{order.volume:.2f}")
            self._set_item(row, 4, f"{order.open_price:,.{d}f}")
            self._set_item(row, 5, f"{order.current_price:,.{d}f}")
            self._set_item(row, 6, f"{order.sl:,.{d}f}" if order.sl else "—")
            self._set_item(row, 7, f"{order.tp:,.{d}f}" if order.tp else "—")

            profit_sign = "+" if order.profit >= 0 else ""
            profit_item = QTableWidgetItem(f"{profit_sign}{order.profit:,.2f}")
            profit_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            profit_color = QColor(COLORS["green"]) if order.profit >= 0 else QColor(COLORS["red"])
            profit_item.setForeground(profit_color)
            self._table.setItem(row, 8, profit_item)

            self._set_item(row, 9, format_dt(order.open_time, self._tz_name))
            self._table.setCellWidget(row, 10, self._make_action_widget(order.ticket, order.volume))

        self._close_all_btn.setEnabled(bool(orders))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_item(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if col in (3, 4, 5, 6, 7, 8):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    _ACTIONS_COL = len(_COLUMNS) - 1  # index 10
    _ACTIONS_COMPACT_WIDTH = 235  # fixed width just enough for all 4 buttons at normal padding

    # Total compact content width (visible columns + Actions); caller adds chrome offset
    COMPACT_CONTENT_WIDTH = sum(_COMPACT_COL_WIDTHS.values()) + _ACTIONS_COMPACT_WIDTH

    def set_compact_mode(self, compact: bool) -> None:
        self._compact = compact
        self._title_label.setVisible(not compact)
        self._compact_equity_lbl.setVisible(compact)
        self._compact_pl_lbl.setVisible(compact)
        hh = self._table.horizontalHeader()

        for col_idx, col_name in enumerate(_COLUMNS):
            hidden = compact and col_idx in _COMPACT_HIDDEN_COLS
            self._table.setColumnHidden(col_idx, hidden)
            if hidden:
                self._table.setColumnWidth(col_idx, 0)
            elif col_name == "Actions":
                pass  # handled separately below
            elif compact and col_name in _COMPACT_COL_WIDTHS:
                # Switch to Fixed so column width doesn't shift with live data
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(col_idx, _COMPACT_COL_WIDTHS[col_name])
            elif not compact:
                # Restore auto-fit for normal mode
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.ResizeToContents)

        if compact:
            hh.setStretchLastSection(False)
            self._table.setColumnWidth(self._ACTIONS_COL, self._ACTIONS_COMPACT_WIDTH)
            # Hide scrollbar so it doesn't reserve space and leave a gap
            self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            hh.setStretchLastSection(True)
            self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._rebuild_action_widgets()

    def update_compact_stats(self, equity: float, pl: float) -> None:
        self._compact_equity_lbl.setText(f"EQUITY  ${equity:,.2f}")
        sign = "+" if pl >= 0 else ""
        color = COLORS["green"] if pl >= 0 else COLORS["red"]
        self._compact_pl_lbl.setText(f"P/L  {sign}${pl:,.2f}")
        self._compact_pl_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: bold;"
            f" font-family: Consolas, monospace; padding: 0 6px;"
        )

    def _rebuild_action_widgets(self) -> None:
        actions_col = self._ACTIONS_COL
        for row in range(self._table.rowCount()):
            ticket_item = self._table.item(row, 0)
            volume_item = self._table.item(row, 3)
            if ticket_item is None:
                continue
            try:
                ticket = int(ticket_item.text())
                volume = float(volume_item.text()) if volume_item else 0.0
            except ValueError:
                continue
            self._table.setCellWidget(row, actions_col, self._make_action_widget(ticket, volume))

    def _make_action_widget(self, ticket: int, volume: float) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(container)

        layout.setContentsMargins(8, 2, 12, 2)
        layout.setSpacing(6)
        btn_padding = "1px 12px"

        layout.addStretch()

        btn_specs = [
            ("Close", COLORS["red"],   100.0),
            ("50%",   COLORS["amber"],  50.0),
            ("80%",   COLORS["amber"],  80.0),
            ("90%",   COLORS["amber"],  90.0),
        ]

        for label, color, pct in btn_specs:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color}; color: #1a1a2e; "
                f"border-radius: 3px; font-size: 11px; font-weight: bold; padding: {btn_padding}; }}"
                f"QPushButton:hover {{ background-color: {COLORS['btn_hover']}; color: {COLORS['text']}; }}"
            )
            btn.clicked.connect(lambda checked=False, t=ticket, p=pct: self.close_order_requested.emit(t, p))
            layout.addWidget(btn)

        return container
