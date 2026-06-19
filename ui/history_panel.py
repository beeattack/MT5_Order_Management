from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QAbstractItemView, QDateTimeEdit,
)
from PySide6.QtCore import Qt, QDate, QDateTime, QTime, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat

from models.history_entry import HistoryEntry
from core.constants import source_icon, source_label
from utils.timezone_manager import format_dt, localize_naive, convert_dt, DEFAULT_TZ

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

_COLUMNS = ["Ticket", "Symbol", "Type", "Exit", "Volume",
            "Open Price", "Close Price", "Profit",
            "Open Time", "Close Time"]
_COL = {name: i for i, name in enumerate(_COLUMNS)}

# Closing-type mark: label, color, tooltip
_EXIT_DISPLAY = {
    "TP":     ("TP",     COLORS["green"],   "Take profit hit"),
    "SL":     ("SL",     COLORS["red"],     "Stop loss hit"),
    "MANUAL": ("Manual", COLORS["subtext"], "Manual close"),
    "EXPERT": ("EA",     COLORS["amber"],   "Closed by Expert Advisor"),
    "SO":     ("SO",     COLORS["red"],     "Stop out / margin call"),
    "OTHER":  ("—",      COLORS["subtext"], "Other / rollover"),
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
QLabel#winRateLabel {{
    font-size: 24px;
    font-weight: bold;
    padding: 2px 12px;
}}
QLabel#summaryLabel {{
    color: {COLORS['subtext']};
    font-size: 12px;
    padding: 0px 12px 2px 12px;
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
QDateTimeEdit {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
}}
QDateTimeEdit::drop-down {{
    border: none;
    background-color: {COLORS['accent']};
    width: 18px;
    border-radius: 0px 4px 4px 0px;
}}
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
    background-color: {COLORS['accent']};
    border: none;
    width: 14px;
}}
QCalendarWidget {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
}}
QCalendarWidget QToolButton {{
    background-color: {COLORS['accent']};
    color: {COLORS['text']};
    border: none;
    border-radius: 3px;
    padding: 3px 8px;
    font-weight: bold;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {COLORS['btn_hover']};
}}
QCalendarWidget QMenu {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
}}
QCalendarWidget QSpinBox {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['text']};
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {COLORS['subtext']};
}}
QCalendarWidget #qt_calendar_navigationbar {{
    background-color: {COLORS['accent']};
    padding: 2px;
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
"""


class HistoryPanel(QWidget):
    filter_requested = Signal(object, object)   # (from_datetime, to_datetime)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._tz_name = DEFAULT_TZ
        self._last_entries: list[HistoryEntry] = []
        self._last_summary: dict = {}
        self._last_win_rate: float = 0.0
        self._build_ui()

    def set_timezone(self, tz_name: str) -> None:
        self._tz_name = tz_name
        if self._last_entries:
            self.update_history(self._last_entries, self._last_summary, self._last_win_rate)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # --- Top row: title + win rate ---
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        title = QLabel("Trade History")
        title.setObjectName("panelTitle")
        top_row.addWidget(title)

        top_row.addStretch()

        self._win_rate_label = QLabel("Win Rate: —")
        self._win_rate_label.setObjectName("winRateLabel")
        self._win_rate_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._win_rate_label)

        layout.addLayout(top_row)

        # --- Stats row: total / wins / losses / net P/L ---
        self._summary_label = QLabel("Total: 0 | Wins: 0 | Losses: 0 | Net P/L: $0.00")
        self._summary_label.setObjectName("summaryLabel")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._summary_label)

        # --- Filter row ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        from_lbl = QLabel("From:")
        from_lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 12px;")
        filter_row.addWidget(from_lbl)

        self._from_dt = QDateTimeEdit()
        self._from_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._from_dt.setCalendarPopup(True)
        default_from = datetime.now() - timedelta(days=30)
        self._from_dt.setDateTime(QDateTime(
            QDate(default_from.year, default_from.month, default_from.day),
            QTime(0, 0, 0)
        ))
        self._from_dt.setFixedWidth(160)
        self._setup_calendar(self._from_dt)
        filter_row.addWidget(self._from_dt)

        to_lbl = QLabel("To:")
        to_lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 12px;")
        filter_row.addWidget(to_lbl)

        self._to_dt = QDateTimeEdit()
        self._to_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._to_dt.setCalendarPopup(True)
        now = datetime.now()
        self._to_dt.setDateTime(QDateTime(
            QDate(now.year, now.month, now.day),
            QTime(now.hour, now.minute, 0)
        ))
        self._to_dt.setFixedWidth(160)
        self._setup_calendar(self._to_dt)
        filter_row.addWidget(self._to_dt)

        self._today_btn = QPushButton("Today")
        self._today_btn.setFixedWidth(70)
        self._today_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['amber']}; color: #1a1a2e; "
            f"border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {COLORS['btn_hover']}; color: {COLORS['text']}; }}"
        )
        self._today_btn.clicked.connect(self._on_today_clicked)
        filter_row.addWidget(self._today_btn)

        self._filter_btn = QPushButton("Filter")
        self._filter_btn.setFixedWidth(70)
        self._filter_btn.clicked.connect(self._on_filter_clicked)
        filter_row.addWidget(self._filter_btn)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # --- Table ---
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setShowGrid(True)
        self._table.setFont(QFont("Consolas", 11))

        hh = self._table.horizontalHeader()
        col_widths = {
            "Ticket": 80, "Symbol": 90, "Type": 60, "Exit": 82, "Volume": 70,
            "Open Price": 95, "Close Price": 95, "Profit": 90,
            "Open Time": 150, "Close Time": 150,
        }
        for col_idx, name in enumerate(_COLUMNS):
            if name == "Close Time":
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Stretch)
            elif name == "Ticket":  # fit content
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.ResizeToContents)
            else:
                hh.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(col_idx, col_widths[name])

        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Calendar setup
    # ------------------------------------------------------------------

    def _setup_calendar(self, dte: QDateTimeEdit) -> None:
        cal = dte.calendarWidget()
        if cal is None:
            return
        today_fmt = QTextCharFormat()
        today_fmt.setBackground(QColor(COLORS["amber"]))
        today_fmt.setForeground(QColor("#1a1a2e"))
        today_fmt.setFontWeight(QFont.Weight.Bold)
        cal.setDateTextFormat(QDate.currentDate(), today_fmt)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_today_clicked(self) -> None:
        now_local = convert_dt(datetime.now(timezone.utc), self._tz_name)
        today = QDate(now_local.year, now_local.month, now_local.day)
        self._from_dt.setDateTime(QDateTime(today, QTime(0, 0, 0)))
        self._to_dt.setDateTime(QDateTime(today, QTime(23, 59, 59)))
        self._on_filter_clicked()

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._last_entries = []
        self._win_rate_label.setText("Win Rate: —")
        self._win_rate_label.setStyleSheet("")
        self._summary_label.setText("Total: 0 | Wins: 0 | Losses: 0 | Net P/L: $0.00")

    def _on_filter_clicked(self) -> None:
        from_naive = self._from_dt.dateTime().toPython()
        to_naive   = self._to_dt.dateTime().toPython()
        # Localize picker values to the selected timezone so MT5 query uses correct UTC range
        from_aware = localize_naive(from_naive, self._tz_name)
        to_aware   = localize_naive(to_naive,   self._tz_name)
        self.filter_requested.emit(from_aware, to_aware)

    # ------------------------------------------------------------------
    # Public update method
    # ------------------------------------------------------------------

    def update_history(
        self,
        entries: list[HistoryEntry],
        summary: dict,
        win_rate: float,
    ) -> None:
        self._last_entries  = entries
        self._last_summary  = summary
        self._last_win_rate = win_rate

        # Win rate label
        wr_text  = f"Win Rate: {win_rate:.1f}%"
        wr_color = COLORS["green"] if win_rate >= 50 else COLORS["red"]
        self._win_rate_label.setText(wr_text)
        self._win_rate_label.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {wr_color}; padding: 2px 12px;"
        )

        # Table
        self._table.setRowCount(0)
        self._table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            self._set_item(row, _COL["Ticket"], str(entry.ticket))

            sym_item = QTableWidgetItem(f"{source_icon(entry.is_auto)}  {entry.symbol}")
            sym_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            sym_item.setToolTip(source_label(entry.is_auto))
            self._table.setItem(row, _COL["Symbol"], sym_item)

            type_item = QTableWidgetItem(entry.order_type)
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            type_color = QColor(COLORS["green"]) if entry.order_type == "BUY" else QColor(COLORS["red"])
            type_item.setForeground(type_color)
            self._table.setItem(row, _COL["Type"], type_item)

            self._set_exit_item(row, entry.close_reason)

            self._set_item(row, _COL["Volume"], f"{entry.volume:.2f}", align_right=True)
            self._set_item(row, _COL["Open Price"], f"{entry.open_price:,.{entry.digits}f}", align_right=True)
            self._set_item(row, _COL["Close Price"], f"{entry.close_price:,.{entry.digits}f}", align_right=True)

            profit_sign  = "+" if entry.profit >= 0 else ""
            profit_item  = QTableWidgetItem(f"{profit_sign}{entry.profit:,.2f}")
            profit_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            profit_color = QColor(COLORS["green"]) if entry.profit >= 0 else QColor(COLORS["red"])
            profit_item.setForeground(profit_color)
            self._table.setItem(row, _COL["Profit"], profit_item)

            self._set_item(row, _COL["Open Time"], format_dt(entry.open_time,  self._tz_name))
            self._set_item(row, _COL["Close Time"], format_dt(entry.close_time, self._tz_name))

        self._table.resizeColumnToContents(_COL["Ticket"])

        # Summary bar
        net = summary.get("net_profit", 0.0)
        net_sign = "+" if net >= 0 else ""
        net_color = COLORS["green"] if net >= 0 else COLORS["red"]
        wins_color = COLORS["green"]
        losses_color = COLORS["red"]

        self._summary_label.setText(
            f"Total: {summary.get('total', 0)}  |  "
            f"<span style='color:{wins_color}'>Wins: {summary.get('wins', 0)}</span>  |  "
            f"<span style='color:{losses_color}'>Losses: {summary.get('losses', 0)}</span>  |  "
            f"Net P/L: <span style='color:{net_color}'>${net_sign}{net:.2f}</span>"
        )
        self._summary_label.setTextFormat(Qt.TextFormat.RichText)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_item(self, row: int, col: int, text: str, align_right: bool = False) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def _set_exit_item(self, row: int, reason: str) -> None:
        label, color, tip = _EXIT_DISPLAY.get(reason or "OTHER", _EXIT_DISPLAY["OTHER"])
        item = QTableWidgetItem(label)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Consolas", 11)
        font.setBold(reason in ("TP", "SL", "SO"))
        item.setFont(font)
        item.setToolTip(tip)
        self._table.setItem(row, _COL["Exit"], item)
