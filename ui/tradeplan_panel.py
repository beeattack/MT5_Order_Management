from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSlider,
    QPushButton, QCheckBox, QDoubleSpinBox,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPen

from core import trade_plan as tp

# Pastel accents on the app's dark base
COLORS = {
    "bg":        "#1a1a2e",
    "panel":     "#16213e",
    "accent":    "#0f3460",
    "text":      "#eaeaea",
    "subtext":   "#a0a0b0",
    "btn":       "#0f3460",
    "btn_hover": "#1a4a8a",
    "mint":      "#88d8b0",   # pastel green
    "coral":     "#ff8b94",   # pastel red
    "peach":     "#ffd3a5",   # pastel amber
    "lavender":  "#b8a9f5",   # pastel violet
    "ring_bg":   "#22304f",
}

_PANEL_QSS = f"""
QWidget {{ background-color: {COLORS['bg']}; color: {COLORS['text']}; }}
QLabel#cardKey {{
    color: {COLORS['subtext']}; font-size: 11px; font-weight: bold;
    letter-spacing: 1px; background: transparent;
}}
QLabel#cardSub {{ color: {COLORS['subtext']}; font-size: 11px; background: transparent; }}
QPushButton#refreshBtn {{
    background-color: {COLORS['btn']}; color: {COLORS['text']}; border: none;
    border-radius: 4px; padding: 5px 16px; font-size: 12px; font-weight: bold;
}}
QPushButton#refreshBtn:hover {{ background-color: {COLORS['btn_hover']}; }}
QSlider::groove:horizontal {{ height: 6px; background: {COLORS['accent']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['peach']}, stop:1 {COLORS['coral']});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px; background: {COLORS['text']}; border-radius: 7px; margin: -4px 0;
}}
QCheckBox {{ color: {COLORS['subtext']}; font-size: 11px; background: transparent; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid {COLORS['accent']}; background: {COLORS['panel']};
}}
QCheckBox::indicator:checked {{ background: {COLORS['mint']}; border-color: {COLORS['mint']}; }}
QDoubleSpinBox {{
    background-color: {COLORS['panel']}; color: {COLORS['mint']};
    border: 1px solid {COLORS['accent']}; border-radius: 4px; padding: 2px 6px;
    font-family: Consolas, monospace; font-size: 13px; font-weight: bold;
}}
QDoubleSpinBox:disabled {{ color: {COLORS['subtext']}; }}
"""

# Banner styling per plan status: (gradient stops, border color, title, subtitle)
_BANNER = {
    "NONE": (
        (COLORS["panel"], COLORS["panel"]), COLORS["accent"],
        "NO TRADE PLAN",
        "Connect to MT5 — the plan builds from your last profitable day",
    ),
    tp.ACTIVE: (
        ("#25436b", "#2d5c55"), COLORS["mint"],
        "PLAN ACTIVE — TRADE WITHIN LIMITS",
        "",
    ),
    tp.LIMIT_HIT: (
        ("#5e3440", "#6e4348"), COLORS["coral"],
        "🛑  DAILY LIMIT HIT — STOP TRADING",
        "Close the terminal and come back tomorrow. Protecting capital IS the plan.",
    ),
    tp.TARGET_REACHED: (
        ("#2d5548", "#356a58"), COLORS["mint"],
        "🎯  TARGET REACHED — PROTECT YOUR PROFIT",
        "Goal met. Anything more is a gift — don't give the day back.",
    ),
}


class ProgressDonut(QWidget):
    """Donut progress chart: pastel arc, big % in the center, caption and
    value line underneath."""

    RING_D = 118
    THICKNESS = 15

    def __init__(self, caption: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caption = caption
        self._color = QColor(color)
        self._fraction: float | None = None   # None = no data
        self._value_text = "—"
        self.setMinimumSize(200, 178)

    def set_value(self, fraction: float | None, value_text: str) -> None:
        self._fraction = fraction
        self._value_text = value_text
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        rx = (w - self.RING_D) / 2
        ry = 8
        ring = QRectF(rx, ry, self.RING_D, self.RING_D)

        # background ring
        pen = QPen(QColor(COLORS["ring_bg"]), self.THICKNESS)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawArc(ring, 0, 360 * 16)

        # progress arc — clamp the drawing at 100%, the label can exceed it
        if self._fraction is not None and self._fraction > 0:
            pen = QPen(self._color, self.THICKNESS)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            span = -int(360 * 16 * min(1.0, self._fraction))
            p.drawArc(ring, 90 * 16, span)

        # center percentage
        if self._fraction is None:
            center, center_color = "—", QColor(COLORS["subtext"])
        else:
            pct = min(self._fraction * 100.0, 999.0)
            center, center_color = f"{pct:.0f}%", self._color
        p.setPen(center_color)
        p.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        p.drawText(ring, Qt.AlignmentFlag.AlignCenter, center)

        # caption + values under the ring
        p.setPen(QColor(COLORS["subtext"]))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRectF(0, ry + self.RING_D + 8, w, 16),
                   Qt.AlignmentFlag.AlignHCenter, self._caption)
        p.setPen(QColor(COLORS["text"]))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(QRectF(0, ry + self.RING_D + 26, w, 16),
                   Qt.AlignmentFlag.AlignHCenter, self._value_text)


class TradePlanPanel(QWidget):
    """Daily plan: base = last profitable day's net profit; today's max
    drawdown = a user percentage of that; target = 2x the drawdown limit,
    or a manual amount the user sets."""

    dd_pct_changed    = Signal(int)
    target_pct_changed = Signal(int)          # target as % of the drawdown limit
    target_changed    = Signal(bool, float)   # (manual_enabled, amount)
    refresh_requested = Signal()

    DEFAULT_TARGET_PCT = 200   # 2x the drawdown limit

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_PANEL_QSS)
        self._base: tp.BaseDay | None = None
        self._searched = False       # a refresh ran but found no profitable day
        self._realized = 0.0
        self._floating = 0.0
        self._build_ui()
        self._recompute()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # ---- status banner ----
        self._banner = QFrame()
        self._banner.setFixedHeight(64)
        banner_lay = QVBoxLayout(self._banner)
        banner_lay.setContentsMargins(18, 8, 18, 8)
        banner_lay.setSpacing(2)
        self._banner_title = QLabel("—")
        self._banner_title.setStyleSheet(
            "font-size: 17px; font-weight: bold; letter-spacing: 1px; background: transparent;"
        )
        self._banner_sub = QLabel("")
        self._banner_sub.setStyleSheet(
            f"color: {COLORS['subtext']}; font-size: 11px; background: transparent;"
        )
        banner_lay.addWidget(self._banner_title)
        banner_lay.addWidget(self._banner_sub)
        layout.addWidget(self._banner)

        # ---- hero cards row ----
        cards = QHBoxLayout()
        cards.setSpacing(10)

        # Base day card (lavender)
        self._base_card, base_lay = self._make_card(COLORS["lavender"], "#332d4d")
        base_lay.addWidget(self._card_key("💜  BASE — LAST PROFITABLE DAY"))
        self._base_val = self._card_value(COLORS["lavender"])
        base_lay.addWidget(self._base_val)
        self._base_sub = self._card_sub()
        base_lay.addWidget(self._base_sub)
        cards.addWidget(self._base_card, 1)

        # Drawdown card (coral) — holds the % slider
        self._dd_card, dd_lay = self._make_card(COLORS["coral"], "#4a3038")
        dd_lay.addWidget(self._card_key("🛑  TODAY'S MAX DRAWDOWN"))
        self._dd_val = self._card_value(COLORS["coral"])
        dd_lay.addWidget(self._dd_val)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)
        self._dd_slider = QSlider(Qt.Orientation.Horizontal)
        self._dd_slider.setRange(10, 150)
        self._dd_slider.setSingleStep(5)
        self._dd_slider.setPageStep(10)
        self._dd_slider.setValue(100)
        self._dd_slider.valueChanged.connect(self._on_pct_changed)
        slider_row.addWidget(self._dd_slider, 1)
        self._dd_pct_lbl = QLabel("100%")
        self._dd_pct_lbl.setStyleSheet(
            f"color: {COLORS['peach']}; font-size: 12px; font-weight: bold;"
            f" font-family: Consolas, monospace; background: transparent;"
        )
        self._dd_pct_lbl.setFixedWidth(44)
        slider_row.addWidget(self._dd_pct_lbl)
        dd_lay.addLayout(slider_row)

        self._dd_sub = self._card_sub("drag to set % of base")
        dd_lay.addWidget(self._dd_sub)
        cards.addWidget(self._dd_card, 1)

        # Target card (mint) — % of the drawdown limit, or a manual amount
        self._target_card, tgt_lay = self._make_card(COLORS["mint"], "#2d4a41")
        tgt_lay.addWidget(self._card_key("🎯  TODAY'S TARGET"))
        self._target_val = self._card_value(COLORS["mint"])
        tgt_lay.addWidget(self._target_val)

        # Target-percentage slider (of the drawdown limit) — active unless manual
        tgt_slider_row = QHBoxLayout()
        tgt_slider_row.setSpacing(8)
        self._tgt_slider = QSlider(Qt.Orientation.Horizontal)
        self._tgt_slider.setRange(50, 500)
        self._tgt_slider.setSingleStep(10)
        self._tgt_slider.setPageStep(25)
        self._tgt_slider.setValue(self.DEFAULT_TARGET_PCT)
        self._tgt_slider.valueChanged.connect(self._on_target_pct_changed)
        tgt_slider_row.addWidget(self._tgt_slider, 1)
        self._tgt_pct_lbl = QLabel(f"{self.DEFAULT_TARGET_PCT}%")
        self._tgt_pct_lbl.setStyleSheet(
            f"color: {COLORS['peach']}; font-size: 12px; font-weight: bold;"
            f" font-family: Consolas, monospace; background: transparent;"
        )
        self._tgt_pct_lbl.setFixedWidth(44)
        tgt_slider_row.addWidget(self._tgt_pct_lbl)
        tgt_lay.addLayout(tgt_slider_row)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(8)
        self._manual_chk = QCheckBox("Manual target")
        self._manual_chk.toggled.connect(self._on_manual_toggled)
        manual_row.addWidget(self._manual_chk)
        self._manual_spin = QDoubleSpinBox()
        self._manual_spin.setRange(0.0, 1_000_000.0)
        self._manual_spin.setDecimals(2)
        self._manual_spin.setSingleStep(50.0)
        self._manual_spin.setPrefix("$ ")
        self._manual_spin.setEnabled(False)
        self._manual_spin.valueChanged.connect(self._on_manual_amount)
        manual_row.addWidget(self._manual_spin, 1)
        tgt_lay.addLayout(manual_row)

        self._target_sub = self._card_sub("drag to set target as % of the drawdown limit")
        tgt_lay.addWidget(self._target_sub)
        cards.addWidget(self._target_card, 1)

        layout.addLayout(cards)

        # ---- today so far ----
        today_frame = QFrame()
        today_frame.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['panel']}; border: 1px solid {COLORS['accent']};"
            f" border-radius: 8px; }}"
        )
        today_lay = QVBoxLayout(today_frame)
        today_lay.setContentsMargins(16, 10, 16, 12)
        today_lay.setSpacing(4)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)
        title = QLabel("TODAY SO FAR")
        title.setObjectName("cardKey")
        stats_row.addWidget(title)
        stats_row.addStretch()
        self._realized_lbl = self._stat_block(stats_row, "REALIZED")
        self._floating_lbl = self._stat_block(stats_row, "FLOATING")
        self._total_lbl = self._stat_block(stats_row, "TOTAL")
        today_lay.addLayout(stats_row)

        donuts = QHBoxLayout()
        donuts.setSpacing(20)
        donuts.addStretch()
        self._dd_donut = ProgressDonut("DRAWDOWN USED", COLORS["coral"])
        donuts.addWidget(self._dd_donut)
        self._tgt_donut = ProgressDonut("PROGRESS TO TARGET", COLORS["mint"])
        donuts.addWidget(self._tgt_donut)
        donuts.addStretch()
        today_lay.addLayout(donuts)

        layout.addWidget(today_frame)

        # ---- footer ----
        footer = QHBoxLayout()
        self._note = QLabel("")
        self._note.setObjectName("cardSub")
        footer.addWidget(self._note)
        footer.addStretch()
        refresh_btn = QPushButton("↻  Recalculate")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.clicked.connect(self.refresh_requested)
        footer.addWidget(refresh_btn)
        layout.addLayout(footer)

        layout.addStretch()

    def _make_card(self, border: str, tint: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {tint}, stop:1 {COLORS['panel']});"
            f" border: 1px solid {border}; border-radius: 10px; }}"
        )
        card.setMinimumHeight(128)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(4)
        return card, lay

    @staticmethod
    def _card_key(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("cardKey")
        return lbl

    @staticmethod
    def _card_value(color: str) -> QLabel:
        lbl = QLabel("—")
        lbl.setStyleSheet(
            f"color: {color}; font-size: 26px; font-weight: bold;"
            f" font-family: Consolas, monospace; background: transparent;"
        )
        return lbl

    @staticmethod
    def _card_sub(text: str = "") -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("cardSub")
        return lbl

    @staticmethod
    def _stat_block(row: QHBoxLayout, key: str) -> QLabel:
        block = QVBoxLayout()
        block.setSpacing(0)
        k = QLabel(key)
        k.setObjectName("cardKey")
        k.setAlignment(Qt.AlignmentFlag.AlignRight)
        v = QLabel("—")
        v.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 16px; font-weight: bold;"
            f" font-family: Consolas, monospace; background: transparent;"
        )
        block.addWidget(k)
        block.addWidget(v)
        row.addLayout(block)
        return v

    # ------------------------------------------------------------------
    # Slots / public API
    # ------------------------------------------------------------------

    def _on_pct_changed(self, value: int) -> None:
        self._dd_pct_lbl.setText(f"{value}%")
        self._recompute()
        self.dd_pct_changed.emit(value)

    def _on_target_pct_changed(self, value: int) -> None:
        self._tgt_pct_lbl.setText(f"{value}%")
        self._recompute()
        self.target_pct_changed.emit(value)

    def _on_manual_toggled(self, checked: bool) -> None:
        self._manual_spin.setEnabled(checked)
        self._tgt_slider.setEnabled(not checked)   # slider drives the auto target
        # Seed an empty manual amount with the current auto target so the
        # user starts from something sensible instead of $0
        if checked and self._manual_spin.value() <= 0 and self._base is not None:
            auto = self._auto_target(tp.drawdown_limit(self._base.profit, self._dd_slider.value()))
            self._manual_spin.setValue(round(auto, 2))
        self._recompute()
        self.target_changed.emit(checked, self._manual_spin.value())

    def _on_manual_amount(self, value: float) -> None:
        if self._manual_chk.isChecked():
            self._recompute()
            self.target_changed.emit(True, value)

    def set_dd_pct(self, pct: int) -> None:
        self._dd_slider.setValue(max(10, min(150, int(pct))))

    def dd_pct(self) -> int:
        return self._dd_slider.value()

    def set_target_pct(self, pct: int) -> None:
        self._tgt_slider.setValue(max(50, min(500, int(pct))))

    def target_pct(self) -> int:
        return self._tgt_slider.value()

    def set_target_config(self, manual: bool, amount: float) -> None:
        """Restore the persisted manual-target setting."""
        self._manual_spin.blockSignals(True)
        self._manual_spin.setValue(max(0.0, amount))
        self._manual_spin.blockSignals(False)
        self._manual_chk.setChecked(manual)   # triggers recompute via toggled
        self._manual_spin.setEnabled(manual)
        self._recompute()

    def set_plan(self, base: tp.BaseDay | None) -> None:
        self._base = base
        self._searched = True
        self._recompute()

    def update_today(self, realized: float, floating: float) -> None:
        self._realized = realized
        self._floating = floating
        self._recompute()

    def clear(self) -> None:
        self._base = None
        self._searched = False
        self._realized = 0.0
        self._floating = 0.0
        self._recompute()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _money(v: float, signed: bool = True) -> str:
        sign = "+" if (signed and v >= 0) else ""
        return f"{sign}${v:,.2f}"

    def _set_money_label(self, lbl: QLabel, v: float) -> None:
        color = COLORS["mint"] if v >= 0 else COLORS["coral"]
        lbl.setText(self._money(v))
        lbl.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: bold;"
            f" font-family: Consolas, monospace; background: transparent;"
        )

    def _auto_target(self, limit: float) -> float:
        """Target from the slider percentage of the drawdown limit."""
        return limit * self._tgt_slider.value() / 100.0

    def _effective_target(self, limit: float) -> float:
        if self._manual_chk.isChecked():
            return self._manual_spin.value()
        return self._auto_target(limit)

    def _recompute(self) -> None:
        pct = self._dd_slider.value()

        if self._base is None:
            self._base_val.setText("—")
            self._dd_val.setText("—")
            self._target_val.setText("—")
            self._base_sub.setText(
                "no profitable day in the last 30 days" if self._searched
                else "connect and recalculate"
            )
            self._dd_donut.set_value(None, "—")
            self._tgt_donut.set_value(None, "—")
            for lbl in (self._realized_lbl, self._floating_lbl, self._total_lbl):
                lbl.setText("—")
            self._note.setText("")
            self._apply_banner("NONE")
            return

        base = self._base.profit
        limit = tp.drawdown_limit(base, pct)
        target = self._effective_target(limit)
        total = self._realized + self._floating

        self._base_val.setText(self._money(base))
        when = f"{self._base.day}  ·  {self._base.days_ago} day(s) ago"
        if self._base.skipped:
            when += f"  ·  skipped {self._base.skipped} losing day(s)"
        self._base_sub.setText(when)

        self._dd_val.setText(f"-${limit:,.2f}")
        self._dd_sub.setText(f"stop trading if today ≤ −${limit:,.2f}")
        self._target_val.setText(f"+${target:,.2f}")
        self._target_sub.setText(
            "your own number — the % slider is off" if self._manual_chk.isChecked()
            else f"{self._tgt_slider.value()}% of the drawdown limit"
        )

        self._set_money_label(self._realized_lbl, self._realized)
        self._set_money_label(self._floating_lbl, self._floating)
        self._set_money_label(self._total_lbl, total)

        dd_used = max(0.0, -total)
        self._dd_donut.set_value(
            dd_used / limit if limit > 0 else None,
            f"-${dd_used:,.2f} / -${limit:,.2f}",
        )
        gain = max(0.0, total)
        self._tgt_donut.set_value(
            gain / target if target > 0 else None,
            f"+${gain:,.2f} / +${target:,.2f}",
        )

        mode = ("manual target" if self._manual_chk.isChecked()
                else f"{self._tgt_slider.value()}% target")
        self._note.setText(
            f"Plan: risk up to {pct}% of {self._base.day}'s profit "
            f"(${base:,.2f}) to make ${target:,.2f}  ·  {mode}"
        )
        self._apply_banner(tp.plan_status(total, limit, target))

    def _apply_banner(self, status: str) -> None:
        stops, border, title, sub = _BANNER[status]
        self._banner.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {stops[0]}, stop:1 {stops[1]});"
            f" border: 1px solid {border}; border-radius: 10px; }}"
        )
        self._banner_title.setText(title)
        if status == tp.ACTIVE:
            limit = tp.drawdown_limit(self._base.profit, self._dd_slider.value())
            target = self._effective_target(limit)
            total = self._realized + self._floating
            room_down = limit + total          # how much further down before limit
            room_up = target - total
            sub = (f"Room to limit: ${max(room_down, 0):,.2f}   ·   "
                   f"To target: ${max(room_up, 0):,.2f}")
        self._banner_sub.setText(sub)
        self._banner_sub.setVisible(bool(sub))
