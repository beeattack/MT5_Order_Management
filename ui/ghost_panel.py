from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
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


def _make_x_icon(size: int = 14, color: str = "#ffffff") -> QIcon:
    """A crisp X drawn with QPainter (reliable at small sizes, unlike a glyph)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 2))
    m = 4
    p.drawLine(m, m, size - m, size - m)
    p.drawLine(size - m, m, m, size - m)
    p.end()
    return QIcon(pm)

_PANEL_QSS = f"""
QWidget#GhostPanel {{ background-color: {COLORS['bg']}; }}
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
    close_order_requested = Signal(int)   # ticket (closes 100%)
    opacity_changed      = Signal(float)  # window opacity 0.30–1.00

    CONTENT_WIDTH = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GhostPanel")
        self.setStyleSheet(_PANEL_QSS)
        self._x_icon = _make_x_icon()
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

        compact_btn = QPushButton("Compact")
        compact_btn.setObjectName("modeBtn")
        compact_btn.clicked.connect(self.switch_compact)
        header.addWidget(compact_btn)

        normal_btn = QPushButton("Normal")
        normal_btn.setObjectName("modeBtn")
        normal_btn.clicked.connect(self.switch_normal)
        header.addWidget(normal_btn)

        layout.addLayout(header)

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

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Symbol", "P/L", ""])
        self._table.horizontalHeader().setVisible(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setFont(QFont("Consolas", 11))
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 86)
        self._table.setColumnWidth(2, 30)
        layout.addWidget(self._table)

    def _on_opacity(self, value: int) -> None:
        self._opacity_lbl.setText(f"{value}%")
        self.opacity_changed.emit(value / 100.0)

    # ------------------------------------------------------------------
    # Public update API
    # ------------------------------------------------------------------

    def update_orders(self, orders: list[Order]) -> None:
        self._table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            sym = QTableWidgetItem(order.symbol)
            sym.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(row, 0, sym)

            sign = "+" if order.profit >= 0 else ""
            pl = QTableWidgetItem(f"{sign}{order.profit:,.2f}")
            pl.setFlags(Qt.ItemFlag.ItemIsEnabled)
            pl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            pl.setForeground(QColor(COLORS["green"] if order.profit >= 0 else COLORS["red"]))
            self._table.setItem(row, 1, pl)

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
            self._table.setCellWidget(row, 2, btn)

    def update_total(self, profit: float) -> None:
        sign = "+" if profit >= 0 else ""
        color = COLORS["green"] if profit >= 0 else COLORS["red"]
        self._total.setText(f"{sign}${profit:,.2f}")
        self._total.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold; font-family: Consolas, monospace;"
        )
