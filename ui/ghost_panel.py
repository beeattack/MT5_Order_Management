from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSizeGrip,
)
from PySide6.QtCore import Qt, Signal, QSize
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


class GhostPanel(QWidget):
    """Minimal always-on-top overlay: active orders with P/L and a close button,
    plus quick switches back to Compact / Normal mode."""

    switch_normal        = Signal()
    switch_compact       = Signal()
    close_order_requested = Signal(object)   # ticket (closes 100%); object avoids
    #                                          Qt's 32-bit int limit for large MT5 tickets
    opacity_changed      = Signal(float)  # window opacity 0.30–1.00

    CONTENT_WIDTH = 300

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
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        # Bottom resize grip (width is fixed by the window, so this resizes height)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(self))
        layout.addLayout(grip_row)

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
            return

        self._tickets = new_tickets
        self._table.setRowCount(0)
        self._table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            sym = QTableWidgetItem(order.symbol)
            sym.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(row, 0, sym)

            typ = QTableWidgetItem(order.order_type)
            typ.setFlags(Qt.ItemFlag.ItemIsEnabled)
            typ.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            typ.setForeground(QColor(COLORS["green"] if order.order_type == "BUY" else COLORS["red"]))
            self._table.setItem(row, 1, typ)

            vol = QTableWidgetItem(f"{order.volume:.2f}")
            vol.setFlags(Qt.ItemFlag.ItemIsEnabled)
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
            btn.clicked.connect(lambda _=False, t=order.ticket: self.close_order_requested.emit(t))
            self._table.setCellWidget(row, 4, btn)

    def _set_pl(self, row: int, profit: float) -> None:
        sign = "+" if profit >= 0 else ""
        item = QTableWidgetItem(f"{sign}{profit:,.2f}")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
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
