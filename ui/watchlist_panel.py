from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTextEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from core import trend_detector as td
from core.watchlist import TIMEFRAMES, DEFAULT_TIMEFRAME

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

_STATE_COLOR = {
    td.UP:      COLORS["green"],
    td.DOWN:    COLORS["red"],
    td.CHOPPY:  COLORS["amber"],
    td.UNKNOWN: COLORS["subtext"],
}
_STATE_LABEL = {
    td.UP:      "▲ UP TREND",
    td.DOWN:    "▼ DOWN TREND",
    td.CHOPPY:  "~ choppy",
    td.UNKNOWN: "—",
}

_COLUMNS = ["Symbol", "Trend", "ADX", "+DI", "−DI", "Updated", ""]

_PANEL_QSS = f"""
QWidget {{ background-color: {COLORS['bg']}; color: {COLORS['text']}; }}
QLabel#panelTitle {{ font-size: 14px; font-weight: bold; padding: 6px 0 4px 4px; }}
QLabel#fieldLabel {{ color: {COLORS['subtext']}; font-size: 11px; }}
QLineEdit, QComboBox {{
    background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']}; border-radius: 4px; padding: 3px 7px; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; background-color: {COLORS['accent']}; width: 16px;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QComboBox QAbstractItemView {{ background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']}; selection-background-color: {COLORS['accent']}; }}
QPushButton {{ background-color: {COLORS['btn']}; color: {COLORS['text']}; border: none;
    border-radius: 4px; padding: 5px 14px; font-size: 12px; font-weight: bold; }}
QPushButton:hover {{ background-color: {COLORS['btn_hover']}; }}
QPushButton:checked {{ background-color: {COLORS['accent']}; }}
QTableWidget {{ background-color: {COLORS['panel']}; alternate-background-color: {COLORS['row_alt']};
    color: {COLORS['text']}; gridline-color: {COLORS['accent']}; border: 1px solid {COLORS['accent']}; font-size: 12px; }}
QHeaderView::section {{ background-color: {COLORS['accent']}; color: {COLORS['text']};
    font-weight: bold; border: none; padding: 4px 6px; font-size: 11px; }}
QTextEdit {{ background-color: {COLORS['panel']}; color: {COLORS['text']};
    border: 1px solid {COLORS['accent']}; border-radius: 4px; font-family: Consolas, monospace; font-size: 11px; }}
QScrollBar:vertical {{ background: {COLORS['panel']}; width: 10px; border: none; }}
QScrollBar::handle:vertical {{ background: {COLORS['accent']}; border-radius: 5px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


class WatchlistPanel(QWidget):
    add_requested        = Signal(str)
    remove_requested     = Signal(str)
    timeframe_changed    = Signal(str)
    watch_toggled        = Signal(bool)
    mute_toggled         = Signal(bool)
    test_sound_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._row_of: dict[str, int] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        title = QLabel("Watchlist — trend alerts (ADX, clear trend vs choppy)")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        # --- controls ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self._symbol_input = QLineEdit()
        self._symbol_input.setPlaceholderText("Symbol e.g. GOLD#")
        self._symbol_input.setFixedWidth(150)
        self._symbol_input.returnPressed.connect(self._emit_add)
        ctrl.addWidget(self._symbol_input)

        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(70)
        add_btn.clicked.connect(self._emit_add)
        ctrl.addWidget(add_btn)

        tf_lbl = QLabel("Timeframe:")
        tf_lbl.setObjectName("fieldLabel")
        ctrl.addWidget(tf_lbl)
        self._tf_combo = QComboBox()
        self._tf_combo.addItems(TIMEFRAMES)
        self._tf_combo.setCurrentText(DEFAULT_TIMEFRAME)
        self._tf_combo.setFixedWidth(80)
        self._tf_combo.currentTextChanged.connect(self.timeframe_changed)
        ctrl.addWidget(self._tf_combo)

        ctrl.addStretch()

        self._mute_btn = QPushButton("🔔 Sound On")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setFixedWidth(120)
        self._mute_btn.toggled.connect(self._on_mute)
        ctrl.addWidget(self._mute_btn)

        test_btn = QPushButton("Test")
        test_btn.setFixedWidth(60)
        test_btn.clicked.connect(self.test_sound_requested)
        ctrl.addWidget(test_btn)

        self._watch_btn = QPushButton("Start Watching")
        self._watch_btn.setCheckable(True)
        self._watch_btn.setFixedWidth(140)
        self._watch_btn.toggled.connect(self._on_watch_toggle)
        ctrl.addWidget(self._watch_btn)

        layout.addLayout(ctrl)

        # --- table ---
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setFont(QFont("Consolas", 11))
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for i in range(2, len(_COLUMNS)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        # --- alert log ---
        log_lbl = QLabel("Alert log")
        log_lbl.setObjectName("fieldLabel")
        layout.addWidget(log_lbl)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        self._log.setMaximumHeight(120)
        layout.addWidget(self._log)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _emit_add(self) -> None:
        sym = self._symbol_input.text().strip()
        if sym:
            self.add_requested.emit(sym)
            self._symbol_input.clear()

    def _on_mute(self, checked: bool) -> None:
        self._mute_btn.setText("🔕 Muted" if checked else "🔔 Sound On")
        self.mute_toggled.emit(checked)

    def _on_watch_toggle(self, checked: bool) -> None:
        self._watch_btn.setText("Stop Watching" if checked else "Start Watching")
        self._watch_btn.setStyleSheet(
            (f"QPushButton {{ background-color: {COLORS['amber']}; color: #1a1a2e; }}"
             f"QPushButton:hover {{ background-color: #f5c45a; }}") if checked else ""
        )
        self.watch_toggled.emit(checked)

    # ------------------------------------------------------------------
    # Public API (driven by MainWindow / monitor callbacks)
    # ------------------------------------------------------------------

    def load_config(self, symbols: list[str], timeframe: str, muted: bool) -> None:
        self._tf_combo.blockSignals(True)
        self._tf_combo.setCurrentText(timeframe)
        self._tf_combo.blockSignals(False)
        self._mute_btn.setChecked(muted)
        self.set_symbols(symbols)

    def set_symbols(self, symbols: list[str]) -> None:
        self._table.setRowCount(0)
        self._row_of.clear()
        for sym in symbols:
            self._append_row(sym)

    def add_symbol_row(self, symbol: str) -> None:
        if symbol not in self._row_of:
            self._append_row(symbol)

    def remove_symbol_row(self, symbol: str) -> None:
        row = self._row_of.get(symbol)
        if row is None:
            return
        self._table.removeRow(row)
        # rebuild index map after removal
        self._row_of = {}
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None:
                self._row_of[item.text()] = r

    def _append_row(self, symbol: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_of[symbol] = row

        sym_item = QTableWidgetItem(symbol)
        sym_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._table.setItem(row, 0, sym_item)
        for col in range(1, 6):
            it = QTableWidgetItem("—")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if col >= 2:
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, col, it)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(26, 22)
        remove_btn.setToolTip(f"Remove {symbol}")
        remove_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['red']}; color: #fff; border-radius: 3px; "
            f"font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #c0392b; }}"
        )
        remove_btn.clicked.connect(lambda _=False, s=symbol: self.remove_requested.emit(s))
        self._table.setCellWidget(row, 6, remove_btn)

    def update_row(self, symbol: str, reading) -> None:
        row = self._row_of.get(symbol)
        if row is None:
            return
        color = _STATE_COLOR.get(reading.state, COLORS["subtext"])

        trend_item = QTableWidgetItem(_STATE_LABEL.get(reading.state, "—"))
        trend_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        trend_item.setForeground(QColor(color))
        f = QFont("Consolas", 11)
        f.setBold(reading.is_clear)
        trend_item.setFont(f)
        self._table.setItem(row, 1, trend_item)

        def num(v):
            return f"{v:.1f}" if v == v else "—"   # NaN check

        self._set_num(row, 2, num(reading.adx))
        self._set_num(row, 3, num(reading.plus_di))
        self._set_num(row, 4, num(reading.minus_di))
        self._set_num(row, 5, datetime.now().strftime("%H:%M:%S"))

    def _set_num(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def log_alert(self, symbol: str, reading) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        word = "UP trend" if reading.state == td.UP else "DOWN trend"
        self._log.append(
            f"[{stamp}] 🔔 {symbol}: clear {word} (ADX {reading.adx:.0f}) — possible entry"
        )

    def set_watching(self, watching: bool) -> None:
        self._watch_btn.blockSignals(True)
        self._watch_btn.setChecked(watching)
        self._watch_btn.setText("Stop Watching" if watching else "Start Watching")
        self._watch_btn.blockSignals(False)
