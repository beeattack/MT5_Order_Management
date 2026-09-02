from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QAbstractItemView, QDateTimeEdit, QDateEdit, QComboBox,
    QStyledItemDelegate,
)
from PySide6.QtCore import Qt, QDate, QDateTime, QTime, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QBrush, QPalette

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
    selection-background-color: {COLORS['btn_hover']};
}}
QTableWidget::item:selected {{
    background-color: {COLORS['btn_hover']};
}}
QHeaderView::section:hover {{
    background-color: {COLORS['btn_hover']};
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
QDateEdit::drop-down {{
    border: none;
    background-color: {COLORS['accent']};
    width: 18px;
    border-radius: 0px 4px 4px 0px;
}}
QComboBox#timePicker {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
}}
QComboBox#timePicker:hover {{
    border: 1px solid {COLORS['btn_hover']};
}}
QComboBox#timePicker::drop-down {{
    border: none;
    background-color: {COLORS['accent']};
    width: 18px;
    border-radius: 0px 4px 4px 0px;
}}
QComboBox#timePicker QAbstractItemView {{
    background-color: {COLORS['panel']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['accent']};
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['text']};
    outline: none;
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


# Selectable times of day: every half hour, plus an explicit end-of-day
# entry so a "To" filter can cover the final 29 minutes of a day.
_TIME_SLOTS: list[QTime] = (
    [QTime(h, m) for h in range(24) for m in (0, 30)] + [QTime(23, 59, 59)]
)


# Sort keys live here so columns order by value, not by their formatted text
# ("1,234.56", "+12.30", "2026-08-19 14:05" all sort wrongly as strings).
_SORT_ROLE = Qt.ItemDataRole.UserRole
_CELL_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class _SortableItem(QTableWidgetItem):
    """Cell that compares on its stored sort key, falling back to text."""

    def __lt__(self, other):
        mine = self.data(_SORT_ROLE)
        theirs = other.data(_SORT_ROLE) if isinstance(other, QTableWidgetItem) else None
        if mine is not None and theirs is not None:
            try:
                return mine < theirs
            except TypeError:
                pass
        return super().__lt__(other)


class _KeepColorDelegate(QStyledItemDelegate):
    """Keep each cell's own text color on the selected row.

    Qt paints selected text with the palette's HighlightedText, which would
    flatten the green/red profit and BUY/SELL coloring exactly on the row the
    user is looking at. Feeding the item's own color back in as
    HighlightedText keeps it.
    """

    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        color = fg.color() if isinstance(fg, QBrush) else fg
        if isinstance(color, QColor) and color.isValid():
            option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


class _HistoryTable(QTableWidget):
    """Table whose row selection toggles: clicking the highlighted row clears
    it, so a click selects and a second click on the same row resets it."""

    def mousePressEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and index.isValid()
                and self.selectionModel().isRowSelected(index.row())):
            self.clearSelection()
            event.accept()
            return
        super().mousePressEvent(event)


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

        default_from = datetime.now() - timedelta(days=30)
        self._from_date, self._from_time = self._add_dt_picker(
            filter_row, "From:",
            QDateTime(
                QDate(default_from.year, default_from.month, default_from.day),
                QTime(0, 0, 0),
            ),
        )

        now = datetime.now()
        self._to_date, self._to_time = self._add_dt_picker(
            filter_row, "To:",
            QDateTime(
                QDate(now.year, now.month, now.day),
                QTime(now.hour, now.minute, 0),
            ),
        )

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
        self._table = _HistoryTable(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setItemDelegate(_KeepColorDelegate(self._table))
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

        # Header-click sorting; clicking the same header again flips the
        # direction. Seeded to Close Time descending, which is the order
        # HistoryManager already returns, so the first view is unchanged.
        hh.setSortIndicator(_COL["Close Time"], Qt.SortOrder.DescendingOrder)
        hh.setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)

        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Calendar setup
    # ------------------------------------------------------------------

    def _add_dt_picker(
        self, row: QHBoxLayout, label: str, initial: QDateTime
    ) -> tuple[QDateEdit, QComboBox]:
        """Add a "label [date] [time]" group to *row* and return both editors.

        The time is a separate dropdown of half-hour slots rather than part
        of a QDateTimeEdit, whose time sections are only reachable by clicking
        into them and typing once a calendar popup is enabled.
        """
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 12px;")
        row.addWidget(lbl)

        date_edit = QDateEdit(initial.date())
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setCalendarPopup(True)
        date_edit.setFixedWidth(108)
        self._setup_calendar(date_edit)
        row.addWidget(date_edit)

        time_box = QComboBox()
        time_box.setObjectName("timePicker")
        for slot in _TIME_SLOTS:
            time_box.addItem(slot.toString("HH:mm"), slot)
        time_box.setMaxVisibleItems(14)
        time_box.setFixedWidth(80)
        time_box.setToolTip("Time of day, in half-hour steps")
        self._select_time(time_box, initial.time())
        row.addWidget(time_box)

        return date_edit, time_box

    @staticmethod
    def _select_time(box: QComboBox, t: QTime) -> None:
        """Select *t* in a time dropdown, rounding up to the next listed slot."""
        for i, slot in enumerate(_TIME_SLOTS):
            if slot >= t:
                box.setCurrentIndex(i)
                return
        box.setCurrentIndex(len(_TIME_SLOTS) - 1)

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
        self._from_date.setDate(today)
        self._select_time(self._from_time, QTime(0, 0, 0))
        self._to_date.setDate(today)
        self._select_time(self._to_time, QTime(23, 59, 59))
        self._on_filter_clicked()

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._last_entries = []
        self._win_rate_label.setText("Win Rate: —")
        self._win_rate_label.setStyleSheet("")
        self._summary_label.setText("Total: 0 | Wins: 0 | Losses: 0 | Net P/L: $0.00")

    def _on_filter_clicked(self) -> None:
        from_naive = QDateTime(self._from_date.date(), self._from_time.currentData()).toPython()
        to_naive   = QDateTime(self._to_date.date(),   self._to_time.currentData()).toPython()
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

        # Sorting must be off while filling: with it on, each inserted row is
        # re-sorted immediately and the next setItem lands on the wrong row.
        self._table.setSortingEnabled(False)

        for row, entry in enumerate(entries):
            self._set_item(row, _COL["Ticket"], str(entry.ticket), sort_key=entry.ticket)

            sym_item = _SortableItem(f"{source_icon(entry.is_auto)}  {entry.symbol}")
            sym_item.setFlags(_CELL_FLAGS)
            sym_item.setData(_SORT_ROLE, entry.symbol)   # sort on the name, not the icon
            sym_item.setToolTip(source_label(entry.is_auto))
            self._table.setItem(row, _COL["Symbol"], sym_item)

            type_item = _SortableItem(entry.order_type)
            type_item.setFlags(_CELL_FLAGS)
            type_item.setData(_SORT_ROLE, entry.order_type)
            type_color = QColor(COLORS["green"]) if entry.order_type == "BUY" else QColor(COLORS["red"])
            type_item.setForeground(type_color)
            self._table.setItem(row, _COL["Type"], type_item)

            self._set_exit_item(row, entry.close_reason)

            self._set_item(row, _COL["Volume"], f"{entry.volume:.2f}",
                           align_right=True, sort_key=entry.volume)
            self._set_item(row, _COL["Open Price"], f"{entry.open_price:,.{entry.digits}f}",
                           align_right=True, sort_key=entry.open_price)
            self._set_item(row, _COL["Close Price"], f"{entry.close_price:,.{entry.digits}f}",
                           align_right=True, sort_key=entry.close_price)

            profit_sign  = "+" if entry.profit >= 0 else ""
            profit_item  = _SortableItem(f"{profit_sign}{entry.profit:,.2f}")
            profit_item.setFlags(_CELL_FLAGS)
            profit_item.setData(_SORT_ROLE, entry.profit)
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            profit_color = QColor(COLORS["green"]) if entry.profit >= 0 else QColor(COLORS["red"])
            profit_item.setForeground(profit_color)
            self._table.setItem(row, _COL["Profit"], profit_item)

            self._set_item(row, _COL["Open Time"], format_dt(entry.open_time, self._tz_name),
                           sort_key=entry.open_time.timestamp())
            self._set_item(row, _COL["Close Time"], format_dt(entry.close_time, self._tz_name),
                           sort_key=entry.close_time.timestamp())

        # Re-applies whichever column/direction the user last clicked
        self._table.setSortingEnabled(True)
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

    def _set_item(self, row: int, col: int, text: str, align_right: bool = False,
                  sort_key=None) -> None:
        item = _SortableItem(text)
        item.setFlags(_CELL_FLAGS)
        item.setData(_SORT_ROLE, text if sort_key is None else sort_key)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def _set_exit_item(self, row: int, reason: str) -> None:
        label, color, tip = _EXIT_DISPLAY.get(reason or "OTHER", _EXIT_DISPLAY["OTHER"])
        item = _SortableItem(label)
        item.setFlags(_CELL_FLAGS)
        item.setData(_SORT_ROLE, reason or "OTHER")
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Consolas", 11)
        font.setBold(reason in ("TP", "SL", "SO"))
        item.setFont(font)
        item.setToolTip(tip)
        self._table.setItem(row, _COL["Exit"], item)
