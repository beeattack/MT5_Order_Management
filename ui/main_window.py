from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QMessageBox, QDialog, QTextBrowser, QSystemTrayIcon,
)
from PySide6.QtCore import Qt, QTimer

from version import __version__, APP_NAME, AUTHOR, YEAR, GITHUB_URL, DESCRIPTION

from ui.connection_panel import ConnectionPanel
from ui.orders_panel     import OrdersPanel
from ui.history_panel    import HistoryPanel
from ui.autotrade_panel  import AutoTradePanel
from ui.dashboard_panel  import DashboardPanel
from ui.watchlist_panel  import WatchlistPanel
from ui.tradeplan_panel  import TradePlanPanel
from ui.ghost_panel      import GhostPanel

from core.auto_trader import AutoTrader
from core.watchlist import WatchlistMonitor, market_watch_symbols
from core.settings_store import SettingsStore
from core import trade_plan
from core import analytics
from core import mt5_alert_bridge
from utils.sound import play_alert

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
QMenuBar {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border-bottom: 1px solid {COLORS['accent']};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 12px;
}}
QMenuBar::item:selected {{
    background-color: {COLORS['accent']};
}}
QMenu {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
}}
QMenu::item {{
    padding: 5px 24px;
}}
QMenu::item:selected {{
    background-color: {COLORS['accent']};
}}
QTextBrowser {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: none;
    padding: 8px 14px;
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

        self.settings = SettingsStore()

        self._connected = False
        self._mode = "normal"        # "normal" | "compact" | "ghost"
        self._compact_mode = False
        ghost_opacity_pct = int(self.settings.get("ghost_opacity_pct", 92))
        self._ghost_opacity = ghost_opacity_pct / 100.0   # window opacity used in ghost mode
        # Last height the user resized the ghost overlay to; reused on re-entry.
        self._ghost_height = max(150, int(self.settings.get("ghost_height", 260)))

        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        self.resize(840, 700)          # 30% narrower default than the old 1200
        self.setMinimumSize(820, 500)
        self.setStyleSheet(_GLOBAL_QSS)

        self._build_ui()
        self._restore_settings()

        self.auto_trader = AutoTrader(
            self.order_mgr,
            self.connector,
            log_cb=self._autotrade_panel.append_log,
            stats_cb=self._autotrade_panel.update_stats,
        )

        self.watchlist = WatchlistMonitor(
            self.connector,
            update_cb=self._watchlist_panel.update_row,
            alert_cb=self._on_watch_alert,
        )
        # reflect the persisted watchlist in the panel
        self._watchlist_panel.load_config(
            self.watchlist.symbols, self.watchlist.muted
        )

        # Tray icon for desktop trend-alert notifications
        self._tray = QSystemTrayIcon(self.windowIcon(), self)
        self._tray.setToolTip("MT5 Order Manager")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

        self._setup_timers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_menu()

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
        self._conn_panel.ghost_requested.connect(lambda: self._apply_mode("ghost"))
        self._conn_panel.timezone_changed.connect(self._on_timezone_changed)
        layout.addWidget(self._conn_panel)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._orders_panel = OrdersPanel()
        self._orders_panel.close_order_requested.connect(self._on_close_order)
        self._orders_panel.close_all_requested.connect(self._on_close_all_orders)

        self._history_panel = HistoryPanel()
        self._history_panel.filter_requested.connect(self._on_filter_history)

        self._dashboard_panel = DashboardPanel()
        self._dashboard_panel.period_changed.connect(self._on_dashboard_period)

        self._autotrade_panel = AutoTradePanel()
        self._autotrade_panel.start_requested.connect(self._on_autotrade_start)
        self._autotrade_panel.stop_requested.connect(self._on_autotrade_stop)
        self._autotrade_panel.kill_requested.connect(self._on_autotrade_kill)

        self._watchlist_panel = WatchlistPanel()
        self._watchlist_panel.add_requested.connect(self._on_watch_add)
        self._watchlist_panel.remove_requested.connect(self._on_watch_remove)
        self._watchlist_panel.watch_toggled.connect(self._on_watch_toggle)
        self._watchlist_panel.mute_toggled.connect(self._on_watch_mute)
        self._watchlist_panel.test_sound_requested.connect(self._on_watch_test)

        self._tradeplan_panel = TradePlanPanel()
        self._tradeplan_panel.dd_pct_changed.connect(self._on_plan_pct_changed)
        self._tradeplan_panel.target_changed.connect(self._on_plan_target_changed)
        self._tradeplan_panel.refresh_requested.connect(self._refresh_trade_plan)

        # Dashboard is the leftmost tab and the default landing view
        self._tabs.addTab(self._dashboard_panel, "Dashboard")
        self._tabs.addTab(self._tradeplan_panel, "Trade Plan")
        self._tabs.addTab(self._orders_panel, "Active Orders")
        self._tabs.addTab(self._history_panel, "History")
        self._tabs.addTab(self._watchlist_panel, "Watchlist")
        self._tabs.addTab(self._autotrade_panel, "Auto Trade")
        self._tabs.setCurrentWidget(self._dashboard_panel)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs)

        # Ghost mode overlay — hidden until activated
        self._ghost_panel = GhostPanel()
        self._ghost_panel.switch_normal.connect(lambda: self._apply_mode("normal"))
        self._ghost_panel.switch_compact.connect(lambda: self._apply_mode("compact"))
        self._ghost_panel.close_order_requested.connect(lambda t: self._on_close_order(t, 100.0))
        self._ghost_panel.opacity_changed.connect(self._on_ghost_opacity)
        self._ghost_panel.setVisible(False)
        layout.addWidget(self._ghost_panel)

    def _restore_settings(self) -> None:
        """Apply persisted settings to the freshly-built widgets."""
        saved_tz = self.settings.get("timezone")
        if saved_tz:
            # Setting the combo emits timezone_changed → panels + re-save (no-op).
            self._conn_panel.set_selected_tz(saved_tz)

        self._autotrade_panel.load_config(self.settings.get("autotrade") or {})
        self._ghost_panel.set_opacity_pct(int(self._ghost_opacity * 100))
        self._tradeplan_panel.set_dd_pct(int(self.settings.get("tradeplan_dd_pct", 100)))
        self._tradeplan_panel.set_target_config(
            bool(self.settings.get("tradeplan_target_manual", False)),
            float(self.settings.get("tradeplan_target_amount", 0.0)),
        )

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Help")
        manual_action = help_menu.addAction("User Manual")
        manual_action.triggered.connect(self._show_manual)
        help_menu.addSeparator()
        about_action = help_menu.addAction(f"About {APP_NAME}")
        about_action.triggered.connect(self._show_about)

    # ------------------------------------------------------------------
    # Help dialogs
    # ------------------------------------------------------------------

    @staticmethod
    def _readme_path() -> str:
        # Works from source (project root is ui/'s parent) and from the
        # PyInstaller bundle (README.md is collected at the bundle root)
        base = getattr(sys, "_MEIPASS", None)
        if base is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "README.md")

    def _show_manual(self) -> None:
        try:
            with open(self._readme_path(), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = "# User Manual\n\nThe manual file (README.md) could not be found."

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{APP_NAME} — User Manual")
        dialog.resize(780, 640)
        dialog.setStyleSheet(_GLOBAL_QSS)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(text)
        layout.addWidget(browser)

        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p><b>Version {__version__}</b></p>"
            f"<p>{DESCRIPTION}</p>"
            f"<p>© {YEAR} {AUTHOR}</p>"
            f'<p><a href="{GITHUB_URL}">{GITHUB_URL}</a></p>',
        )

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

        # Auto-trade loop — checks for newly-closed bars on the configured TF
        self._autotrade_timer = QTimer(self)
        self._autotrade_timer.setInterval(2000)
        self._autotrade_timer.timeout.connect(self.auto_trader.on_tick)

        # Watchlist trend-scan loop
        self._watchlist_timer = QTimer(self)
        self._watchlist_timer.setInterval(10000)
        self._watchlist_timer.timeout.connect(self.watchlist.on_tick)

        # Trade-plan "today so far" refresh (runs while connected)
        self._plan_timer = QTimer(self)
        self._plan_timer.setInterval(5000)
        self._plan_timer.timeout.connect(self._update_plan_today)

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
            self._on_dashboard_period(*self._dashboard_panel.current_range())
            self._refresh_watch_symbols()
            self._refresh_autotrade_symbols()
            self._refresh_trade_plan()
            self._plan_timer.start()
            if self.watchlist.enabled:
                self._watchlist_timer.start()
                self.watchlist.on_tick()
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to MT5:\n{err}",
            )

    def _on_disconnect(self) -> None:
        self._orders_timer.stop()
        self._autotrade_timer.stop()
        self._watchlist_timer.stop()
        self._plan_timer.stop()
        self._tradeplan_panel.clear()
        self.auto_trader.stop()
        self._autotrade_panel.set_running(False)
        self.connector.disconnect()
        self._connected = False
        self._conn_panel.set_state_detected()
        self._orders_panel.update_orders([])
        self._ghost_panel.update_orders([])
        self._ghost_panel.update_account(0.0, 0.0, 0.0)
        self._history_panel.clear()
        self._dashboard_panel.clear()
        self._detection_timer.start()

    # ------------------------------------------------------------------
    # Slot — close order
    # ------------------------------------------------------------------

    def _on_close_all_orders(self) -> None:
        count = self._orders_panel.order_count()
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
    # Slots — auto trade
    # ------------------------------------------------------------------

    def _on_autotrade_start(self, config: dict) -> None:
        self.settings.set("autotrade", config)
        if not self._connected:
            QMessageBox.warning(
                self, "Not Connected",
                "Connect to MT5 before starting auto-trade.",
            )
            self._autotrade_panel.set_running(False)
            return

        if config.get("mode") == "LIVE":
            reply = QMessageBox.warning(
                self, "Enable LIVE Auto-Trading",
                f"LIVE mode will send REAL market orders for {config.get('symbol')}.\n\n"
                f"Risk per trade: {config.get('risk_pct')}%  |  "
                f"Daily loss limit: {config.get('daily_loss_pct')}%\n\n"
                "Are you sure you want to start live auto-trading?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._autotrade_panel.set_running(False)
                return

        ok, err = self.auto_trader.start(config)
        if not ok:
            QMessageBox.warning(self, "Auto-Trade Failed to Start", err)
            self._autotrade_panel.set_running(False)
            return

        self._autotrade_panel.set_running(True)
        self._autotrade_timer.start()

    def _on_autotrade_stop(self) -> None:
        self._autotrade_timer.stop()
        self.auto_trader.stop()
        self._autotrade_panel.set_running(False)

    def _on_autotrade_kill(self) -> None:
        self._autotrade_timer.stop()
        self.auto_trader.kill()
        self._autotrade_panel.set_running(False)

    # ------------------------------------------------------------------
    # Slots — watchlist
    # ------------------------------------------------------------------

    def _on_watch_add(self, symbol: str) -> None:
        if self._connected and self.connector.is_connected():
            import MetaTrader5 as mt5  # guarded import is fine; only reached when connected
            if mt5.symbol_info(symbol) is None:
                QMessageBox.warning(self, "Unknown Symbol",
                                    f"'{symbol}' was not found at your broker.")
                return
        if self.watchlist.add(symbol):
            self._watchlist_panel.add_symbol_row(symbol)
            if self.watchlist.enabled:
                self.watchlist.on_tick()

    def _on_watch_remove(self, symbol: str) -> None:
        self.watchlist.remove(symbol)
        self._watchlist_panel.remove_symbol_row(symbol)

    def _on_watch_toggle(self, watching: bool) -> None:
        self.watchlist.enabled = watching
        if watching:
            if not self._connected:
                QMessageBox.warning(self, "Not Connected",
                                    "Connect to MT5 before starting the watchlist.")
                self._watchlist_panel.set_watching(False)
                self.watchlist.enabled = False
                return
            self._watchlist_timer.start()
            self.watchlist.on_tick()
        else:
            self._watchlist_timer.stop()

    def _on_watch_mute(self, muted: bool) -> None:
        self.watchlist.set_muted(muted)

    def _on_watch_alert(self, symbol: str, timeframe: str, reading) -> None:
        self._watchlist_panel.log_alert(symbol, timeframe, reading)
        msg = f"{timeframe} clear {reading.state} trend (ADX {reading.adx:.0f}) - possible entry"
        self._notify(f"Trend Alert — {symbol} [{timeframe}]", msg)
        mt5_alert_bridge.write_alert(f"{symbol} {timeframe}: {msg}")
        if not self.watchlist.muted:
            play_alert()

    def _notify(self, title: str, message: str) -> None:
        """Desktop (system tray) notification for trend alerts."""
        if self._tray is not None and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 6000
            )

    def _on_watch_test(self) -> None:
        """Exercise the full alert path: sound + desktop notification + MT5 alert."""
        self._notify("Trend Alert — TEST", "Test alert: sound + desktop + MT5 alert.")
        play_alert()
        wrote = mt5_alert_bridge.write_alert("TEST: MT5 Order Manager watchlist alert")
        if wrote:
            self._watchlist_panel.log_message(
                "Test fired — sound + desktop notification; MT5 alert written "
                "(install the WatchlistAlertBridge indicator in MT5 to see it pop up)."
            )
        else:
            self._watchlist_panel.log_message(
                "Test fired — sound + desktop notification; MT5 alert NOT written "
                "(connect to MT5 first)."
            )

    def _refresh_watch_symbols(self) -> None:
        if self._connected and self.connector.is_connected():
            self._watchlist_panel.set_symbol_choices(market_watch_symbols())

    def _refresh_autotrade_symbols(self) -> None:
        if self._connected and self.connector.is_connected():
            self._autotrade_panel.set_symbol_choices(market_watch_symbols())

    def _on_tab_changed(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if widget is self._watchlist_panel:
            self._refresh_watch_symbols()
        elif widget is self._autotrade_panel:
            self._refresh_autotrade_symbols()
        elif widget is self._tradeplan_panel:
            self._refresh_trade_plan()

    # ------------------------------------------------------------------
    # Slots — trade plan
    # ------------------------------------------------------------------

    def _on_plan_pct_changed(self, pct: int) -> None:
        self.settings.set("tradeplan_dd_pct", pct)

    def _on_plan_target_changed(self, manual: bool, amount: float) -> None:
        self.settings.update({
            "tradeplan_target_manual": manual,
            "tradeplan_target_amount": amount,
        })

    def _refresh_trade_plan(self) -> None:
        """Rebuild the plan base from history (last profitable day)."""
        if not self._connected:
            return
        now = datetime.now(timezone.utc)
        frm, to = trade_plan.lookback_range_utc(now)
        entries = self.history_mgr.get_history(frm, to)
        self._tradeplan_panel.set_plan(trade_plan.find_base_day(entries, now))
        self._update_plan_today()

    def _update_plan_today(self) -> None:
        """Refresh today's realized + floating P/L shown on the plan tab."""
        if not self._connected:
            return
        now = datetime.now(timezone.utc)
        frm, to = trade_plan.today_range_utc(now)
        realized = sum(e.profit for e in self.history_mgr.get_history(frm, to))
        info = self.connector.get_account_info()
        floating = info.get("profit", 0.0) if info else 0.0
        self._tradeplan_panel.update_today(realized, floating)

    # ------------------------------------------------------------------
    # Slot — timezone change
    # ------------------------------------------------------------------

    def _on_timezone_changed(self, tz_name: str) -> None:
        self._orders_panel.set_timezone(tz_name)
        self._history_panel.set_timezone(tz_name)
        self.settings.set("timezone", tz_name)

    # ------------------------------------------------------------------
    # Slot — history filter
    # ------------------------------------------------------------------

    def _on_filter_history(self, from_dt: datetime, to_dt: datetime) -> None:
        entries     = self.history_mgr.get_history(from_dt, to_dt)
        summary     = self.history_mgr.calculate_summary(entries)
        win_rate    = self.history_mgr.calculate_win_rate(entries)
        self._history_panel.update_history(entries, summary, win_rate)

    # ------------------------------------------------------------------
    # Slot — dashboard
    # ------------------------------------------------------------------

    def _on_dashboard_period(self, from_dt: datetime, to_dt: datetime) -> None:
        if not self._connected:
            self._dashboard_panel.clear()
            return
        entries = self.history_mgr.get_history(from_dt, to_dt)
        stats = analytics.compute(entries)
        self._dashboard_panel.update_dashboard(stats, analytics.insights(stats))

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
        if self._mode == "ghost":
            self._ghost_panel.update_orders(orders)
        account_info = self.connector.get_account_info()
        if account_info:
            balance = account_info.get("balance", 0.0)
            equity = account_info.get("equity", 0.0)
            profit = account_info.get("profit", 0.0)
            self._conn_panel.update_account_stats(balance, equity, profit)
            self._dashboard_panel.update_account(balance, equity, profit, len(orders))
            if self._compact_mode:
                self._orders_panel.update_compact_stats(equity, profit)
            elif self._mode == "ghost":
                self._ghost_panel.update_account(balance, equity, profit)

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
    # Display modes: Normal ↔ Compact ↔ Ghost
    # ------------------------------------------------------------------

    def _toggle_display_mode(self) -> None:
        # Connection-panel button toggles between Normal and Compact
        self._apply_mode("compact" if self._mode == "normal" else "normal")

    def _on_ghost_opacity(self, opacity: float) -> None:
        self._ghost_opacity = opacity
        self.settings.set("ghost_opacity_pct", round(opacity * 100))
        if self._mode == "ghost":
            self.setWindowOpacity(opacity)

    def _apply_mode(self, mode: str) -> None:
        # Remember the height the user left the ghost overlay at, so re-entering
        # ghost mode restores it instead of snapping back to the default.
        if self._mode == "ghost" and mode != "ghost":
            self._remember_ghost_height()

        self._mode = mode
        compact = mode == "compact"
        ghost = mode == "ghost"
        self._compact_mode = compact

        # Content visibility
        self.menuBar().setVisible(mode == "normal")
        self._conn_panel.setVisible(not ghost)
        self._tabs.setVisible(not ghost)
        self._ghost_panel.setVisible(ghost)

        if not ghost:
            self._conn_panel.set_compact_layout(compact)
            self._orders_panel.set_compact_mode(compact)
            self._tabs.tabBar().setVisible(not compact)
            if compact:
                self._tabs.setCurrentWidget(self._orders_panel)

        # Clear any fixed-size constraints before changing window flags
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)

        base = (Qt.WindowType.Window | Qt.WindowType.WindowTitleHint |
                Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowCloseButtonHint)

        if mode == "normal":
            self.setWindowOpacity(1.0)
            self.setWindowFlags(base | Qt.WindowType.WindowMinMaxButtonsHint)
            self.show()
            self.setMinimumSize(820, 500)
            self.setMaximumSize(16777215, 16777215)
            self.resize(840, 700)
        elif compact:
            self.setWindowOpacity(1.0)
            self.setWindowFlags(base | Qt.WindowType.WindowMinimizeButtonHint |
                                Qt.WindowType.WindowStaysOnTopHint)
            self.show()
            compact_w = self._orders_panel.COMPACT_CONTENT_WIDTH + 18
            self.setFixedWidth(compact_w)
            self.setMinimumHeight(198)
            self.setMaximumHeight(16777215)
            self.resize(compact_w, 260)
        else:  # ghost — frameless, translucent, always-on-top floating overlay
            self.setWindowOpacity(self._ghost_opacity)
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.show()
            ghost_w = self._ghost_panel.CONTENT_WIDTH
            self.setFixedWidth(ghost_w)              # lock width; grip resizes height only
            self.setMinimumHeight(150)
            self.setMaximumHeight(16777215)
            self.resize(ghost_w, self._ghost_height)
            self._refresh_orders()   # populate immediately

    def _remember_ghost_height(self) -> None:
        self._ghost_height = max(150, self.height())
        self.settings.set("ghost_height", self._ghost_height)

    # ------------------------------------------------------------------
    # Persist settings on exit
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._mode == "ghost":
            self._remember_ghost_height()
        self.settings.update({
            "autotrade": self._autotrade_panel.config(),
            "timezone": self._conn_panel.selected_tz(),
        })
        super().closeEvent(event)
