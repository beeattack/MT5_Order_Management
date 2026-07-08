from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox,
    QTextEdit, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

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
QLabel#fieldLabel {{
    color: {COLORS['subtext']};
    font-size: 11px;
}}
QLabel#statKey {{
    color: {COLORS['subtext']};
    font-size: 11px;
}}
QLabel#statValue {{
    color: {COLORS['text']};
    font-size: 14px;
    font-weight: bold;
    font-family: "Consolas", monospace;
}}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
}}
QComboBox::drop-down {{
    border: none;
    background-color: {COLORS['accent']};
    width: 16px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    selection-background-color: {COLORS['accent']};
}}
QPushButton {{
    background-color: {COLORS['btn']};
    color: {COLORS['text']};
    border: none;
    border-radius: 4px;
    padding: 5px 16px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {COLORS['btn_hover']};
}}
QPushButton:disabled {{
    background-color: {COLORS['accent']};
    color: {COLORS['subtext']};
}}
QTextEdit {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    font-family: "Consolas", monospace;
    font-size: 11px;
}}
"""


class AutoTradePanel(QWidget):
    start_requested = Signal(dict)
    stop_requested  = Signal()
    kill_requested  = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._running = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        title = QLabel("Auto Trade — H1 Swing (EMA + RSI pullback)")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        # --- Config grid ---
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        self._symbol = QComboBox()
        self._symbol.setEditable(True)   # allow symbols not in Market Watch
        self._symbol.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._symbol.setFixedWidth(110)
        self._symbol.setCurrentText("GOLD#")

        self._timeframe = QComboBox()
        self._timeframe.addItems(["M30", "H1", "H4"])
        self._timeframe.setCurrentText("H1")
        self._timeframe.setFixedWidth(80)

        self._mode = QComboBox()
        self._mode.addItems(["PAPER", "LIVE"])
        self._mode.setFixedWidth(90)
        self._mode.currentTextChanged.connect(self._on_mode_changed)

        self._risk = self._spin(QDoubleSpinBox, 0.01, 10.0, 0.5, 0.05, suffix=" %")
        self._max_positions = self._spin(QSpinBox, 1, 20, 1, 1)
        self._daily_loss = self._spin(QDoubleSpinBox, 0.0, 50.0, 3.0, 0.5, suffix=" %")
        self._daily_profit = self._spin(QDoubleSpinBox, 0.0, 100.0, 5.0, 0.5, suffix=" %")
        self._time_stop = self._spin(QSpinBox, 1, 500, 24, 1, suffix=" bars")
        self._max_spread = self._spin(QDoubleSpinBox, 0.0, 2.0, 0.3, 0.05)
        self._session_start = self._spin(QSpinBox, 0, 24, 0, 1, suffix=" h")
        self._session_end = self._spin(QSpinBox, 0, 24, 24, 1, suffix=" h")

        fields = [
            ("Symbol", self._symbol),
            ("Timeframe", self._timeframe),
            ("Mode", self._mode),
            ("Risk / trade", self._risk),
            ("Max positions", self._max_positions),
            ("Daily loss limit", self._daily_loss),
            ("Daily profit target", self._daily_profit),
            ("Time stop", self._time_stop),
            ("Max spread / SL", self._max_spread),
            ("Session start (UTC)", self._session_start),
            ("Session end (UTC)", self._session_end),
        ]
        for i, (label, widget) in enumerate(fields):
            row, col = divmod(i, 3)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            lbl = QLabel(label)
            lbl.setObjectName("fieldLabel")
            cell.addWidget(lbl)
            cell.addWidget(widget)
            grid.addLayout(cell, row, col)

        layout.addLayout(grid)

        # --- Control row ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._start_btn = QPushButton("Start")
        self._start_btn.setFixedWidth(120)
        self._start_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['green']}; color: #1a1a2e; }}"
            f"QPushButton:hover {{ background-color: #00d4a8; }}"
        )
        self._start_btn.clicked.connect(self._on_start_stop)
        controls.addWidget(self._start_btn)

        self._kill_btn = QPushButton("KILL")
        self._kill_btn.setFixedWidth(90)
        self._kill_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['red']}; color: #ffffff; }}"
            f"QPushButton:hover {{ background-color: #c0392b; }}"
        )
        self._kill_btn.clicked.connect(self.kill_requested)
        controls.addWidget(self._kill_btn)

        controls.addStretch()

        # --- Live stats ---
        for key, attr in (("MODE", "_stat_mode"), ("DAILY P/L", "_stat_pnl"),
                          ("OPEN", "_stat_open"), ("TRADES", "_stat_trades")):
            block = QVBoxLayout()
            block.setSpacing(0)
            k = QLabel(key)
            k.setObjectName("statKey")
            k.setAlignment(Qt.AlignmentFlag.AlignRight)
            v = QLabel("—")
            v.setObjectName("statValue")
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            block.addWidget(k)
            block.addWidget(v)
            setattr(self, attr, v)
            controls.addLayout(block)
            controls.addSpacing(10)

        layout.addLayout(controls)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['accent']};")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # --- Decision log ---
        log_lbl = QLabel("Decision log")
        log_lbl.setObjectName("fieldLabel")
        layout.addWidget(log_lbl)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        layout.addWidget(self._log)

        self._on_mode_changed(self._mode.currentText())

    def _spin(self, cls, lo, hi, val, step, suffix: str = ""):
        w = cls()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setValue(val)
        if suffix:
            w.setSuffix(suffix)
        if isinstance(w, QDoubleSpinBox):
            w.setDecimals(2)
        w.setFixedWidth(110)
        return w

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_mode_changed(self, mode: str) -> None:
        if mode == "LIVE" and not self._running:
            self.append_log("⚠ LIVE mode selected — real orders will be sent on Start.")

    def _on_start_stop(self) -> None:
        if self._running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit(self.config())

    def load_config(self, cfg: dict) -> None:
        """Restore previously-saved field values (called once at startup)."""
        if not cfg:
            return
        if cfg.get("symbol"):
            self._symbol.setCurrentText(str(cfg["symbol"]))
        if cfg.get("timeframe"):
            self._timeframe.setCurrentText(str(cfg["timeframe"]))
        if cfg.get("mode") in ("PAPER", "LIVE"):
            self._mode.setCurrentText(cfg["mode"])
        spin_map = {
            "risk_pct": self._risk,
            "max_positions": self._max_positions,
            "daily_loss_pct": self._daily_loss,
            "daily_profit_pct": self._daily_profit,
            "time_stop": self._time_stop,
            "max_spread_frac": self._max_spread,
            "session_start": self._session_start,
            "session_end": self._session_end,
        }
        for key, widget in spin_map.items():
            if key in cfg and cfg[key] is not None:
                try:
                    widget.setValue(type(widget.value())(cfg[key]))
                except (TypeError, ValueError):
                    pass

    def set_symbol_choices(self, symbols: list[str]) -> None:
        """Populate the symbol combo from the MT5 Market Watch, keeping the
        current text (which may be a custom symbol not in the list)."""
        current = self._symbol.currentText()
        self._symbol.blockSignals(True)
        self._symbol.clear()
        self._symbol.addItems(symbols)
        self._symbol.setCurrentText(current)
        self._symbol.blockSignals(False)

    def config(self) -> dict:
        return {
            "symbol": self._symbol.currentText().strip(),
            "timeframe": self._timeframe.currentText(),
            "mode": self._mode.currentText(),
            "risk_pct": self._risk.value(),
            "max_positions": self._max_positions.value(),
            "daily_loss_pct": self._daily_loss.value(),
            "daily_profit_pct": self._daily_profit.value(),
            "time_stop": self._time_stop.value(),
            "max_spread_frac": self._max_spread.value(),
            "session_start": self._session_start.value(),
            "session_end": self._session_end.value(),
        }

    # ------------------------------------------------------------------
    # Public API (called from MainWindow / AutoTrader callbacks)
    # ------------------------------------------------------------------

    def set_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.setText("Stop" if running else "Start")
        self._start_btn.setStyleSheet(
            (f"QPushButton {{ background-color: {COLORS['amber']}; color: #1a1a2e; }}"
             f"QPushButton:hover {{ background-color: #f5c45a; }}") if running else
            (f"QPushButton {{ background-color: {COLORS['green']}; color: #1a1a2e; }}"
             f"QPushButton:hover {{ background-color: #00d4a8; }}")
        )
        # lock config while running
        for w in (self._symbol, self._timeframe, self._mode, self._risk,
                  self._max_positions, self._daily_loss, self._daily_profit,
                  self._time_stop, self._max_spread, self._session_start,
                  self._session_end):
            w.setEnabled(not running)

    def append_log(self, msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log.append(f"[{stamp}] {msg}")

    def update_stats(self, stats: dict) -> None:
        self._stat_mode.setText(stats.get("mode", "—"))
        pnl = stats.get("daily_pnl", 0.0)
        sign = "+" if pnl >= 0 else ""
        self._stat_pnl.setText(f"{sign}{pnl:.2f}")
        self._stat_pnl.setStyleSheet(
            f"color: {COLORS['green'] if pnl >= 0 else COLORS['red']};"
            f" font-size: 14px; font-weight: bold; font-family: Consolas, monospace;"
        )
        self._stat_open.setText(str(stats.get("open_positions", 0)))
        self._stat_trades.setText(str(stats.get("trades_today", 0)))
