from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from utils.timezone_manager import TIMEZONE_OPTIONS, DEFAULT_TZ

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
QWidget#ConnectionPanel {{
    background-color: {COLORS['panel']};
    border-bottom: 1px solid {COLORS['accent']};
}}
QLabel#statValue {{
    color: {COLORS['text']};
    font-size: 13px;
    font-weight: bold;
    font-family: "Consolas", monospace;
}}
QLabel#statKey {{
    color: {COLORS['subtext']};
    font-size: 11px;
}}
QPushButton {{
    background-color: {COLORS['btn']};
    color: {COLORS['text']};
    border: none;
    border-radius: 4px;
    padding: 4px 14px;
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
QComboBox {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
}}
QComboBox:hover {{
    border: 1px solid {COLORS['btn_hover']};
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
    selection-color: {COLORS['text']};
}}
"""

_DIVIDER_QSS = f"background-color: {COLORS['accent']};"


def _make_divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    line.setStyleSheet(_DIVIDER_QSS)
    return line


class ConnectionPanel(QWidget):
    connect_requested    = Signal()
    disconnect_requested = Signal()
    display_mode_toggled = Signal()
    ghost_requested      = Signal()
    timezone_changed     = Signal(str)   # emits IANA timezone name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionPanel")
        self.setFixedHeight(55)
        self.setStyleSheet(_PANEL_QSS)
        self._is_connected   = False
        self._account_name   = ""
        self._compact_layout = False
        self._build_ui()
        self.set_state_not_found()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Status indicator
        self._status_label = QLabel("● MT5 Not Found")
        self._status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._status_label.setMinimumWidth(160)
        layout.addWidget(self._status_label)

        # Divider — always visible (separates status from stats)
        layout.addWidget(_make_divider())

        # Balance block — hidden in compact mode (includes its trailing divider)
        self._balance_widget = QWidget()
        self._balance_widget.setStyleSheet("background: transparent;")
        bal_layout = QHBoxLayout(self._balance_widget)
        bal_layout.setContentsMargins(0, 0, 0, 0)
        bal_layout.setSpacing(10)
        bal_layout.addLayout(self._make_stat_block("BALANCE", "_balance_val"))
        bal_layout.addWidget(_make_divider())
        layout.addWidget(self._balance_widget)

        # Equity + P/L block — hidden in compact mode (shown in orders panel header instead)
        self._equity_pl_widget = QWidget()
        self._equity_pl_widget.setStyleSheet("background: transparent;")
        ep_layout = QHBoxLayout(self._equity_pl_widget)
        ep_layout.setContentsMargins(0, 0, 0, 0)
        ep_layout.setSpacing(10)
        ep_layout.addLayout(self._make_stat_block("EQUITY", "_equity_val"))
        ep_layout.addWidget(_make_divider())
        ep_layout.addLayout(self._make_stat_block("P / L", "_pl_val"))
        layout.addWidget(self._equity_pl_widget)

        layout.addStretch()

        # Timezone selector — hidden in compact mode
        self._tz_widget = QWidget()
        self._tz_widget.setStyleSheet("background: transparent;")
        tz_layout = QHBoxLayout(self._tz_widget)
        tz_layout.setContentsMargins(0, 0, 0, 0)
        tz_layout.setSpacing(4)

        tz_lbl = QLabel("TZ:")
        tz_lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 11px;")
        tz_layout.addWidget(tz_lbl)

        self._tz_combo = QComboBox()
        self._tz_combo.setFixedWidth(185)
        for label, _ in TIMEZONE_OPTIONS:
            self._tz_combo.addItem(label)
        self._tz_combo.currentIndexChanged.connect(self._on_tz_changed)
        tz_layout.addWidget(self._tz_combo)

        layout.addWidget(self._tz_widget)

        # Single connect/disconnect toggle button
        self._toggle_btn = QPushButton("Connect")
        self._toggle_btn.setFixedWidth(105)
        self._toggle_btn.clicked.connect(self._on_toggle_connection)
        layout.addWidget(self._toggle_btn)

        # Display mode toggle button
        self._mode_btn = QPushButton("Compact")
        self._mode_btn.setFixedWidth(82)
        self._mode_btn.clicked.connect(self.display_mode_toggled)
        layout.addWidget(self._mode_btn)

        # Ghost (floating minimal overlay) button
        self._ghost_btn = QPushButton("Ghost")
        self._ghost_btn.setFixedWidth(70)
        self._ghost_btn.clicked.connect(self.ghost_requested)
        layout.addWidget(self._ghost_btn)

    def _make_stat_block(self, key: str, attr: str) -> QHBoxLayout:
        block = QHBoxLayout()
        block.setSpacing(5)
        block.setContentsMargins(6, 0, 6, 0)

        key_lbl = QLabel(key)
        key_lbl.setObjectName("statKey")
        block.addWidget(key_lbl)

        val_lbl = QLabel("—")
        val_lbl.setObjectName("statValue")
        val_lbl.setMinimumWidth(90)
        block.addWidget(val_lbl)

        setattr(self, attr, val_lbl)
        return block

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_toggle_connection(self) -> None:
        if self._is_connected:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit()

    def _on_tz_changed(self, index: int) -> None:
        _, iana = TIMEZONE_OPTIONS[index]
        self.timezone_changed.emit(iana)

    def selected_tz(self) -> str:
        return TIMEZONE_OPTIONS[self._tz_combo.currentIndex()][1]

    def set_selected_tz(self, iana: str) -> None:
        """Select the combo entry for the given IANA name (restored from settings)."""
        for i, (_, name) in enumerate(TIMEZONE_OPTIONS):
            if name == iana:
                self._tz_combo.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # State helpers (called from MainWindow)
    # ------------------------------------------------------------------

    def _set_status(self, text: str, color: str) -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color};")

    def _refresh_status_label(self) -> None:
        if not self._is_connected:
            return
        # Hide account name in compact mode
        if self._compact_layout or not self._account_name:
            self._set_status("● Connected", COLORS["green"])
        else:
            self._set_status(f"● Connected  [{self._account_name}]", COLORS["green"])

    def set_state_not_found(self) -> None:
        self._is_connected  = False
        self._account_name  = ""
        self._set_status("● MT5 Not Found", COLORS["red"])
        self._toggle_btn.setText("Connect")
        self._toggle_btn.setEnabled(False)
        self._toggle_btn.setStyleSheet("")
        self._clear_stats()

    def set_state_detected(self) -> None:
        self._is_connected  = False
        self._account_name  = ""
        self._set_status("● MT5 Running", COLORS["amber"])
        self._toggle_btn.setText("Connect")
        self._toggle_btn.setEnabled(True)
        self._toggle_btn.setStyleSheet("")
        self._clear_stats()

    def set_state_connected(self, account_info: dict | None = None) -> None:
        self._is_connected = True
        self._account_name = ""
        if account_info:
            name = account_info.get("name") or str(account_info.get("login", ""))
            self._account_name = name
        self._refresh_status_label()
        self._toggle_btn.setText("Disconnect")
        self._toggle_btn.setEnabled(True)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['red']}; color: #ffffff; }}"
            f"QPushButton:hover {{ background-color: #c0392b; }}"
        )
        if account_info:
            self.update_account_stats(
                account_info.get("balance", 0.0),
                account_info.get("equity", 0.0),
                account_info.get("profit", 0.0),
            )

    def update_account_stats(self, balance: float, equity: float, profit: float) -> None:
        self._balance_val.setText(f"${balance:,.2f}")
        self._equity_val.setText(f"${equity:,.2f}")

        sign = "+" if profit >= 0 else ""
        color = COLORS["green"] if profit >= 0 else COLORS["red"]
        self._pl_val.setText(f"{sign}${profit:,.2f}")
        self._pl_val.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: bold; font-family: Consolas, monospace;"
        )

    def _clear_stats(self) -> None:
        for attr in ("_balance_val", "_equity_val", "_pl_val"):
            lbl: QLabel = getattr(self, attr)
            lbl.setText("—")
            lbl.setStyleSheet("")

    # ------------------------------------------------------------------
    # Compact layout
    # ------------------------------------------------------------------

    def set_compact_layout(self, compact: bool) -> None:
        self._compact_layout = compact
        self._balance_widget.setVisible(not compact)
        self._equity_pl_widget.setVisible(not compact)
        self._tz_widget.setVisible(not compact)
        self.setFixedHeight(38 if compact else 55)
        self._mode_btn.setText("Normal" if compact else "Compact")
        self._refresh_status_label()
