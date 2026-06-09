from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer

from ui.connection_panel import ConnectionPanel
from ui.orders_panel     import OrdersPanel
from ui.history_panel    import HistoryPanel

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

_GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS['accent']};
    background-color: {COLORS['bg']};
}}
QTabBar::tab {{
    background-color: {COLORS['panel']};
    color: {COLORS['subtext']};
    border: 1px solid {COLORS['accent']};
    border-bottom: none;
    padding: 6px 20px;
    font-size: 12px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    background-color: {COLORS['accent']};
    color: {COLORS['text']};
}}
QTabBar::tab:hover {{
    background-color: {COLORS['btn_hover']};
    color: {COLORS['text']};
}}
QTableWidget {{
    background-color: {COLORS['panel']};
    alternate-background-color: #1e2a4a;
    color: {COLORS['text']};
    gridline-color: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
    selection-background-color: {COLORS['accent']};
}}
QHeaderView::section {{
    background-color: {COLORS['accent']};
    color: {COLORS['text']};
    font-weight: bold;
    border: none;
    padding: 4px 6px;
}}
QPushButton {{
    background-color: {COLORS['btn']};
    color: {COLORS['text']};
    border: none;
    border-radius: 4px;
    padding: 4px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {COLORS['btn_hover']};
}}
QPushButton:disabled {{
    background-color: {COLORS['accent']};
    color: {COLORS['subtext']};
}}
QLineEdit {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 3px 7px;
}}
QLineEdit:focus {{
    border: 1px solid {COLORS['btn_hover']};
}}
QDateTimeEdit {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 3px 6px;
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
QScrollBar:horizontal {{
    background: {COLORS['panel']};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS['accent']};
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QMessageBox {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
}}
QComboBox {{
    background-color: {COLORS['panel']};
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


class MainWindow(QMainWindow):
    def __init__(self, connector, order_mgr, history_mgr) -> None:
        super().__init__()
        self.connector   = connector
        self.order_mgr   = order_mgr
        self.history_mgr = history_mgr

        self._connected = False
        self._compact_mode = False

        self.setWindowTitle("MT5 Order Manager")
        self.resize(1200, 700)
        self.setMinimumSize(900, 500)
        self.setStyleSheet(_GLOBAL_QSS)

        self._build_ui()
        self._setup_timers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Connection bar
        self._conn_panel = ConnectionPanel()
        self._conn_panel.connect_requested.connect(self._on_connect)
        self._conn_panel.disconnect_requested.connect(self._on_disconnect)
        self._conn_panel.display_mode_toggled.connect(self._toggle_display_mode)
        self._conn_panel.timezone_changed.connect(self._on_timezone_changed)
        layout.addWidget(self._conn_panel)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._orders_panel = OrdersPanel()
        self._orders_panel.close_order_requested.connect(self._on_close_order)
        self._orders_panel.close_all_requested.connect(self._on_close_all_orders)
        self._tabs.addTab(self._orders_panel, "Active Orders")

        self._history_panel = HistoryPanel()
        self._history_panel.filter_requested.connect(self._on_filter_history)
        self._tabs.addTab(self._history_panel, "History")

        layout.addWidget(self._tabs)

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _setup_timers(self) -> None:
        self._detection_timer = QTimer(self)
        self._detection_timer.setInterval(3000)
        self._detection_timer.timeout.connect(self._check_mt5_status)
        self._detection_timer.start()

        self._orders_timer = QTimer(self)
        self._orders_timer.setInterval(100)
        self._orders_timer.timeout.connect(self._refresh_orders)

    # ------------------------------------------------------------------
    # Slots — connection
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        self._orders_panel.update_orders([])
        self._history_panel.clear()
        ok, err = self.connector.connect()
        if ok:
            self._connected = True
            account_info = self.connector.get_account_info()
            self._conn_panel.set_state_connected(account_info)
            self._detection_timer.stop()
            self._orders_timer.start()
            self._refresh_orders()
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to MT5:\n{err}",
            )

    def _on_disconnect(self) -> None:
        self._orders_timer.stop()
        self.connector.disconnect()
        self._connected = False
        self._conn_panel.set_state_detected()
        self._orders_panel.update_orders([])
        self._history_panel.clear()
        self._detection_timer.start()

    # ------------------------------------------------------------------
    # Slot — close order
    # ------------------------------------------------------------------

    def _on_close_all_orders(self) -> None:
        count = self._orders_panel._table.rowCount()
        reply = QMessageBox.question(
            self,
            "Close All Orders",
            f"Close all {count} open order(s)?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        closed, failed, errors = self.order_mgr.close_all_orders()
        self._refresh_orders()
        if failed:
            QMessageBox.warning(
                self,
                "Close All — Partial Failure",
                f"Closed: {closed}  |  Failed: {failed}\n\n" + "\n".join(errors),
            )

    def _on_close_order(self, ticket: int, percent: float) -> None:
        ok, err = self.order_mgr.close_percent(ticket, percent)
        if not ok:
            QMessageBox.warning(
                self,
                "Close Order Failed",
                f"Could not close position #{ticket}:\n{err}",
            )
        self._refresh_orders()

    # ------------------------------------------------------------------
    # Slot — timezone change
    # ------------------------------------------------------------------

    def _on_timezone_changed(self, tz_name: str) -> None:
        self._orders_panel.set_timezone(tz_name)
        self._history_panel.set_timezone(tz_name)

    # ------------------------------------------------------------------
    # Slot — history filter
    # ------------------------------------------------------------------

    def _on_filter_history(self, from_dt: datetime, to_dt: datetime) -> None:
        entries     = self.history_mgr.get_history(from_dt, to_dt)
        summary     = self.history_mgr.calculate_summary(entries)
        win_rate    = self.history_mgr.calculate_win_rate(entries)
        self._history_panel.update_history(entries, summary, win_rate)

    # ------------------------------------------------------------------
    # Timer callbacks
    # ------------------------------------------------------------------

    def _refresh_orders(self) -> None:
        if not self._connected:
            return
        if not self.connector.is_connected():
            self._on_disconnect()
            return
        orders = self.order_mgr.get_open_orders()
        self._orders_panel.update_orders(orders)
        account_info = self.connector.get_account_info()
        if account_info:
            self._conn_panel.update_account_stats(
                account_info.get("balance", 0.0),
                account_info.get("equity", 0.0),
                account_info.get("profit", 0.0),
            )

    def _check_mt5_status(self) -> None:
        if self._connected:
            self._detection_timer.stop()
            return
        detected = self.connector.detect()
        if detected:
            self._conn_panel.set_state_detected()
        else:
            self._conn_panel.set_state_not_found()

    # ------------------------------------------------------------------
    # Display mode toggle (Normal ↔ Compact)
    # ------------------------------------------------------------------

    def _toggle_display_mode(self) -> None:
        self._compact_mode = not self._compact_mode
        compact = self._compact_mode

        self._conn_panel.set_compact_layout(compact)
        self._orders_panel.set_compact_mode(compact)

        # Hide tab bar and lock to orders tab in compact mode
        self._tabs.tabBar().setVisible(not compact)
        if compact:
            self._tabs.setCurrentIndex(0)

        if compact:
            # Remove size constraints before setting new flags so resize isn't clamped
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setWindowFlags(
                Qt.WindowType.Window |
                Qt.WindowType.WindowTitleHint |
                Qt.WindowType.WindowSystemMenuHint |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.WindowMinimizeButtonHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.show()
            # Lock width exactly to content, allow height resize only
            compact_w = self._orders_panel.COMPACT_CONTENT_WIDTH + 18
            self.setFixedWidth(compact_w)
            self.setMinimumHeight(220)
            self.setMaximumHeight(16777215)
            self.resize(compact_w, 289)
        else:
            self.setWindowFlags(
                Qt.WindowType.Window |
                Qt.WindowType.WindowTitleHint |
                Qt.WindowType.WindowSystemMenuHint |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.WindowMinMaxButtonsHint
            )
            self.show()
            # Restore full free resizing in normal mode
            self.setMinimumSize(900, 500)
            self.setMaximumSize(16777215, 16777215)
            self.resize(1200, 700)
