from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTextEdit, QDialog, QTextBrowser,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from core import trend_detector as td
from core.watchlist import (
    TIMEFRAMES, TIMEFRAME_LABELS, ALERT_TIMEFRAMES, CONFLUENCE_LABEL,
)

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
# Compact per-timeframe cell labels (columns are narrow)
_STATE_SHORT = {
    td.UP:      "▲ UP",
    td.DOWN:    "▼ DN",
    td.CHOPPY:  "~",
    td.UNKNOWN: "—",
}

# One column per timeframe, each showing that symbol's trend on that timeframe,
# plus an Align column summarising how many timeframes agree.
_TF_COL_START = 1
_ALIGN_COL = _TF_COL_START + len(TIMEFRAMES)
_UPDATED_COL = _ALIGN_COL + 1
_REMOVE_COL = _UPDATED_COL + 1
_COLUMNS = ["Symbol", *(TIMEFRAME_LABELS[tf] for tf in TIMEFRAMES), "Align", "Updated", ""]

# Bold the Align summary when at least this many timeframes agree
_ALIGN_STRONG = 5

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

        title = QLabel("Watchlist — trend alerts")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        # --- controls ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        sym_lbl = QLabel("Symbol:")
        sym_lbl.setObjectName("fieldLabel")
        ctrl.addWidget(sym_lbl)

        self._symbol_combo = QComboBox()
        self._symbol_combo.setEditable(False)
        self._symbol_combo.setPlaceholderText("Connect to load Market Watch")
        self._symbol_combo.setFixedWidth(170)
        ctrl.addWidget(self._symbol_combo)

        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(70)
        add_btn.clicked.connect(self._emit_add)
        ctrl.addWidget(add_btn)

        help_btn = QPushButton("ℹ How trend is derived")
        help_btn.setFixedWidth(170)
        help_btn.setToolTip("Explain how each timeframe's trend is classified")
        help_btn.clicked.connect(self._show_trend_help)
        ctrl.addWidget(help_btn)

        ctrl.addStretch()

        self._mute_btn = QPushButton("🔔 Sound On")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setFixedWidth(120)
        self._mute_btn.toggled.connect(self._on_mute)
        ctrl.addWidget(self._mute_btn)

        test_btn = QPushButton("Test")
        test_btn.setFixedWidth(60)
        test_btn.setToolTip("Test alert — plays the sound and shows a desktop notification")
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
        sym = self._symbol_combo.currentText().strip()
        if sym:
            self.add_requested.emit(sym)

    def set_symbol_choices(self, symbols: list[str]) -> None:
        """Populate the symbol combo from the MT5 Market Watch."""
        current = self._symbol_combo.currentText()
        self._symbol_combo.blockSignals(True)
        self._symbol_combo.clear()
        self._symbol_combo.addItems(symbols)
        idx = self._symbol_combo.findText(current)
        self._symbol_combo.setCurrentIndex(idx if idx >= 0 else -1)
        self._symbol_combo.blockSignals(False)

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

    def _show_trend_help(self) -> None:
        """Explain how each timeframe cell's trend is classified. Built from the
        live trend_detector constants so it stays in sync with the logic."""
        text = f"""# How the trend is derived

Each timeframe cell classifies the symbol's recent **closed** bars as:

- **▲ UP** — a clear up-trend
- **▼ DN** — a clear down-trend
- **~** — choppy / ranging (no clear trend)
- **—** — not enough data yet

Three checks must **all agree** for a clear ▲ / ▼ trend. If any disagree, the
cell is **~ choppy**.

### 1. Strength — ADX (period {td.DEFAULT_ADX_PERIOD})
ADX must be **≥ {td.DEFAULT_ADX_THRESHOLD:.0f}** to *enter* a trend. Below that
the market is treated as ranging (**~**), whatever the direction.

### 2. Direction — +DI / −DI and EMA (period {td.DEFAULT_EMA_PERIOD})
- **▲ UP** needs **+DI &gt; −DI** *and* price **above** the EMA.
- **▼ DN** needs **−DI &gt; +DI** *and* price **below** the EMA.

### 3. Confirmation — RSI (period {td.DEFAULT_RSI_PERIOD})
- **▲ UP** needs **RSI &gt; {td.RSI_MIDLINE + td.RSI_BAND:.0f}**.
- **▼ DN** needs **RSI &lt; {td.RSI_MIDLINE - td.RSI_BAND:.0f}**.

### Stickiness (hysteresis)
Once a trend is established it doesn't flip off at the first wobble: it
**holds** until ADX falls below **{td.ADX_EXIT_THRESHOLD:.0f}**, RSI crosses to
the other side of **{td.RSI_MIDLINE:.0f}±{td.RSI_BAND:.0f}**, or a direction
check fails. This stops the cells — and alerts — from flickering when a value
hovers right at a threshold.

### Align column
Counts the timeframes agreeing on each direction (e.g. **5▲ 1▼**), colored by
the dominant side and bold when {_ALIGN_STRONG}+ agree. Hover it for the
per-timeframe breakdown.

---

Every timeframe (M1 → Day) is evaluated **independently**, using closed bars
only — the still-forming bar is ignored.

Alerts (sound + desktop + MT5) fire only when a timeframe **changes** into a
clear ▲ / ▼ trend — and only for **{", ".join(ALERT_TIMEFRAMES)}** (M1/M5
flip too often). A **confluence alert** fires when **{CONFLUENCE_LABEL}**
all align in the same clear direction."""

        dialog = QDialog(self)
        dialog.setWindowTitle("How trend is derived")
        dialog.resize(560, 560)
        dialog.setStyleSheet(_PANEL_QSS)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setMarkdown(text)
        layout.addWidget(browser)
        dialog.exec()

    # ------------------------------------------------------------------
    # Public API (driven by MainWindow / monitor callbacks)
    # ------------------------------------------------------------------

    def load_config(self, symbols: list[str], muted: bool) -> None:
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
        for col in range(1, _REMOVE_COL):
            it = QTableWidgetItem("—")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self._table.setCellWidget(row, _REMOVE_COL, remove_btn)

    def update_row(self, symbol: str, readings: dict) -> None:
        """readings: {timeframe_name: TrendReading} for this symbol."""
        row = self._row_of.get(symbol)
        if row is None:
            return
        for i, tf_name in enumerate(TIMEFRAMES):
            self._set_trend_cell(row, _TF_COL_START + i, readings.get(tf_name))
        self._set_align_cell(row, readings)
        self._set_num(row, _UPDATED_COL, datetime.now().strftime("%H:%M:%S"))

    def _set_trend_cell(self, row: int, col: int, reading) -> None:
        state = reading.state if reading is not None else td.UNKNOWN
        item = QTableWidgetItem(_STATE_SHORT.get(state, "—"))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(_STATE_COLOR.get(state, COLORS["subtext"])))
        f = QFont("Consolas", 11)
        f.setBold(state in (td.UP, td.DOWN))
        item.setFont(f)
        self._table.setItem(row, col, item)

    def _set_align_cell(self, row: int, readings: dict) -> None:
        """Cross-timeframe summary: how many TFs agree on each direction."""
        ups = sum(1 for r in readings.values() if r is not None and r.state == td.UP)
        downs = sum(1 for r in readings.values() if r is not None and r.state == td.DOWN)
        if ups == 0 and downs == 0:
            text, color, bold = "—", COLORS["subtext"], False
        else:
            text = f"{ups}▲ {downs}▼"
            if ups > downs:
                color = COLORS["green"]
            elif downs > ups:
                color = COLORS["red"]
            else:
                color = COLORS["amber"]
            bold = max(ups, downs) >= _ALIGN_STRONG

        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        f = QFont("Consolas", 11)
        f.setBold(bold)
        item.setFont(f)
        item.setToolTip("\n".join(
            f"{TIMEFRAME_LABELS[tf]}: {readings[tf].state if readings.get(tf) else '—'}"
            for tf in TIMEFRAMES
        ))
        self._table.setItem(row, _ALIGN_COL, item)

    def _set_num(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, col, item)

    def log_alert(self, symbol: str, timeframe: str, reading) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        word = "UP trend" if reading.state == td.UP else "DOWN trend"
        tf_label = TIMEFRAME_LABELS.get(timeframe, timeframe)
        self._log.append(
            f"[{stamp}] 🔔 {symbol} [{tf_label}]: clear {word} "
            f"(ADX {reading.adx:.0f}) — possible entry"
        )

    def log_message(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log.append(f"[{stamp}] {text}")

    def set_watching(self, watching: bool) -> None:
        self._watch_btn.blockSignals(True)
        self._watch_btn.setChecked(watching)
        self._watch_btn.setText("Stop Watching" if watching else "Start Watching")
        self._watch_btn.blockSignals(False)
