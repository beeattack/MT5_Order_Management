"""Interval alarm: a bulb that blinks (and optionally sounds) on clock marks.

Green while waiting, red and blinking while ringing, grey when off.
Double-click opens the settings; a single click stops a ringing alarm.

One `AlarmEngine` holds the state and timing; `AlarmBulb` is only a view onto
it. The main window and the ghost overlay each show a bulb, and because they
share the engine they ring, blink and dismiss together instead of running two
alarms that would sound twice.
"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFileDialog, QFrame,
)
from PySide6.QtCore import Qt, QObject, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen, QFont

from core.interval_alarm import INTERVAL_OPTIONS, DEFAULT_INTERVAL, next_due
from utils.sound import AlarmSound, SOUND_FILTER, is_supported_sound

_GREEN = "#00b894"
_RED = "#e74c3c"
_GREY = "#55596b"
_TEXT = "#eaeaea"
_SUBTEXT = "#a0a0b0"
_BG = "#1a1a2e"
_PANEL = "#16213e"
_ACCENT = "#0f3460"
_BTN_HOVER = "#1a4a8a"

# How long an unattended alarm rings before stopping itself.
RING_SECONDS = 15
_BLINK_MS = 450
_SOUND_POLL_MS = 300

MODE_BLINK = "blink"
MODE_SOUND = "sound"


class AlarmEngine(QObject):
    """Timing, state and sound for the interval alarm."""

    state_changed = Signal()      # repaint the bulbs
    settings_changed = Signal()   # persist
    alarm_fired = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._interval = DEFAULT_INTERVAL
        self._mode = MODE_BLINK
        self._sound_file = ""
        self._due: datetime | None = None
        self._ringing = False
        self._blink_on = False
        self._rang_at: datetime | None = None
        self._shown_minutes: int | None = None   # last countdown value painted
        self._sound = AlarmSound()

        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        self._blink = QTimer(self)
        self._blink.setInterval(_BLINK_MS)
        self._blink.timeout.connect(self._on_blink)

        # keeps the sound going for the whole ring when the file is shorter
        self._sound_poll = QTimer(self)
        self._sound_poll.setInterval(_SOUND_POLL_MS)
        self._sound_poll.timeout.connect(self._on_sound_poll)

    # -- state ---------------------------------------------------------

    def interval(self) -> int:
        return self._interval

    def mode(self) -> str:
        return self._mode

    def sound_file(self) -> str:
        return self._sound_file

    def next_due(self) -> datetime | None:
        return self._due

    def is_ringing(self) -> bool:
        return self._ringing

    def blink_on(self) -> bool:
        return self._blink_on

    def minutes_remaining(self) -> int | None:
        """Whole minutes until the next alarm, rounded up.

        Rounded up so the bulb reads 1 for the final minute rather than
        sitting on 0, and never shows 0 while still counting.
        """
        if self._due is None or self._ringing:
            return None
        seconds = (self._due - datetime.now()).total_seconds()
        if seconds <= 0:
            return 0
        minutes = int(seconds // 60) + (1 if seconds % 60 else 0)
        # rounding up a hair over a whole interval (firing a few ms early)
        # would read as 16 on a 15-minute alarm
        return min(minutes, self._interval)

    def configure(self, interval: int, mode: str = MODE_BLINK,
                  sound_file: str = "", *, emit: bool = False) -> None:
        """Apply settings and re-arm from the clock."""
        valid = {m for m, _ in INTERVAL_OPTIONS}
        self._interval = interval if interval in valid else DEFAULT_INTERVAL
        self._mode = MODE_SOUND if mode == MODE_SOUND else MODE_BLINK
        self._sound_file = sound_file if is_supported_sound(sound_file) else ""
        self.dismiss()
        self._due = next_due(datetime.now(), self._interval)
        self.state_changed.emit()
        if emit:
            self.settings_changed.emit()

    def dismiss(self) -> None:
        """Stop a ringing alarm (user click, or the ring running its course)."""
        if self._ringing:
            self._ringing = False
            self.state_changed.emit()
        self._rang_at = None
        self._blink.stop()
        self._blink_on = False
        self._sound_poll.stop()
        self._sound.stop()

    # -- timing --------------------------------------------------------

    def _on_tick(self) -> None:
        now = datetime.now()
        # repaint when the displayed minute rolls over, not every second
        minutes = self.minutes_remaining()
        if minutes != self._shown_minutes:
            self._shown_minutes = minutes
            self.state_changed.emit()
        if self._ringing:
            if self._rang_at and (now - self._rang_at).total_seconds() >= RING_SECONDS:
                self.dismiss()
            return
        if self._due is None:
            return
        if now >= self._due:
            self._start_ringing(now)
        elif (self._due - now).total_seconds() > self._interval * 60:
            # clock moved backwards (NTP correction, timezone change): re-arm
            self._due = next_due(now, self._interval)
            self.state_changed.emit()

    def _start_ringing(self, now: datetime) -> None:
        self._ringing = True
        self._rang_at = now
        self._blink_on = True
        self._blink.start()
        # computed from now, so a machine waking from sleep rings once rather
        # than working through every boundary it missed
        self._due = next_due(now, self._interval)
        if self._mode == MODE_SOUND:
            self._sound.play(self._sound_file)
            self._sound_poll.start()
        self.state_changed.emit()
        self.alarm_fired.emit()

    def _on_blink(self) -> None:
        self._blink_on = not self._blink_on
        self.state_changed.emit()

    def _on_sound_poll(self) -> None:
        """Replay the file if it finished while the alarm is still ringing."""
        if not self._ringing:
            self._sound_poll.stop()
            return
        if not self._sound.is_playing():
            self._sound.play(self._sound_file)

    def describe(self) -> str:
        """Tooltip text for the bulbs."""
        if self._interval <= 0:
            return "Alarm off - double-click to set an interval"
        label = dict(INTERVAL_OPTIONS)[self._interval]
        if self._ringing:
            return f"Alarm - click to stop  (every {label})"
        due = f"{self._due:%H:%M}" if self._due else "-"
        sound = ""
        if self._mode == MODE_SOUND:
            name = os.path.basename(self._sound_file) if self._sound_file else "default beep"
            sound = f"\nSound: {name}"
        return f"Every {label}, next at {due}{sound}\ndouble-click to change"


class AlarmBulb(QWidget):
    """A view of an AlarmEngine. Several may share one engine."""

    def __init__(self, engine: AlarmEngine, size: int = 34,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        engine.state_changed.connect(self._on_state)
        self._on_state()

    def _on_state(self) -> None:
        self.setToolTip(self._engine.describe())
        self.update()

    # -- interaction ---------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._engine.is_ringing():
            self._engine.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        dlg = AlarmSettingsDialog(self._engine.interval(), self._engine.mode(),
                                  self._engine.sound_file(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._engine.configure(dlg.selected_interval(), dlg.selected_mode(),
                                   dlg.selected_sound(), emit=True)
        event.accept()

    # -- painting ------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._engine.interval() <= 0:
            core, lit = QColor(_GREY), False
        elif self._engine.is_ringing():
            core, lit = QColor(_RED), self._engine.blink_on()
        else:
            core, lit = QColor(_GREEN), True

        inset = self.width() * 0.13
        rect = QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset)
        centre = QPointF(rect.center())
        d = rect.width()
        halo_r = self.width() / 2.0
        p.setPen(Qt.PenStyle.NoPen)

        # 1. halo thrown onto the panel behind
        if lit:
            glow_in, glow_out = QColor(core), QColor(core)
            glow_in.setAlpha(120)
            glow_out.setAlpha(0)
            glow = QRadialGradient(centre, halo_r)
            glow.setColorAt(0.0, glow_in)
            glow.setColorAt(0.55, glow_in)
            glow.setColorAt(1.0, glow_out)
            p.setBrush(glow)
            p.drawEllipse(centre, halo_r, halo_r)

        body = QColor(core) if lit else QColor(core).darker(250)

        # 2. the sphere, lit from the upper left
        lamp = QPointF(centre.x() - d * 0.22, centre.y() - d * 0.26)
        sphere = QRadialGradient(lamp, d * 0.95)
        sphere.setColorAt(0.0, body.lighter(185))
        sphere.setColorAt(0.42, body)
        sphere.setColorAt(1.0, body.darker(175))
        p.setBrush(sphere)
        p.drawEllipse(rect)

        # 3. rim shading: transparent through the middle, dark at the edge,
        #    which is what reads as curvature rather than a flat disc
        edge_clear, edge_dark = QColor(0, 0, 0, 0), QColor(0, 0, 0, 115)
        rim = QRadialGradient(centre, d / 2.0)
        rim.setColorAt(0.0, edge_clear)
        rim.setColorAt(0.72, edge_clear)
        rim.setColorAt(1.0, edge_dark)
        p.setBrush(rim)
        p.drawEllipse(rect)

        # 4. bounce light along the lower edge, opposite the lamp
        if lit:
            bounce_in, bounce_out = QColor(core).lighter(165), QColor(core)
            bounce_in.setAlpha(130)
            bounce_out.setAlpha(0)
            bounce = QRadialGradient(
                QPointF(centre.x() + d * 0.16, centre.y() + d * 0.34), d * 0.5)
            bounce.setColorAt(0.0, bounce_in)
            bounce.setColorAt(1.0, bounce_out)
            p.setBrush(bounce)
            p.drawEllipse(rect)

        # 5. specular highlight, kept small and high so it never sits on the
        #    digits in the middle
        spec_in, spec_out = QColor(255, 255, 255, 205), QColor(255, 255, 255, 0)
        spec_c = QPointF(centre.x() - d * 0.21, centre.y() - d * 0.25)
        spec = QRadialGradient(spec_c, d * 0.27)
        spec.setColorAt(0.0, spec_in)
        spec.setColorAt(1.0, spec_out)
        p.setBrush(spec)
        p.drawEllipse(spec_c, d * 0.25, d * 0.19)

        # 6. a thin dark outline to separate the bulb from the panel
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.drawEllipse(rect)

        # minutes left, centred - dark on the lit face, which reads better
        # against green than white would
        minutes = self._engine.minutes_remaining()
        if minutes is not None:
            text = str(minutes)
            size = max(8, int(d * (0.70 if len(text) < 2 else 0.58)))
            font = QFont("Segoe UI", size, QFont.Weight.Bold)
            font.setPixelSize(size)
            p.setFont(font)
            # a faint light halo under the glyphs keeps them crisp over the
            # shaded sphere
            p.setPen(QColor(255, 255, 255, 70) if lit else QColor(0, 0, 0, 0))
            p.drawText(rect.translated(0, 1), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor("#0d1f33") if lit else QColor(_SUBTEXT))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class AlarmSettingsDialog(QDialog):
    """Interval, blink/sound mode and the sound file."""

    def __init__(self, interval: int, mode: str, sound_file: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alarm Settings")
        self.setModal(True)
        self._sound_file = sound_file if is_supported_sound(sound_file) else ""
        self.setStyleSheet(
            f"QDialog {{ background-color: {_BG}; }}"
            f"QLabel {{ color: {_TEXT}; font-size: 12px; }}"
            f"QLabel#hint {{ color: {_SUBTEXT}; font-size: 11px; }}"
            f"QLabel#file {{ color: {_SUBTEXT}; font-size: 11px;"
            f" background-color: {_PANEL}; border: 1px solid {_ACCENT};"
            f" border-radius: 3px; padding: 4px 6px; }}"
            f"QRadioButton {{ color: {_TEXT}; font-size: 12px; padding: 2px 0; }}"
            f"QFrame#sep {{ background-color: {_ACCENT}; }}"
            f"QPushButton {{ background-color: {_ACCENT}; color: {_TEXT}; border: none;"
            f" border-radius: 4px; padding: 5px 14px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {_BTN_HOVER}; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(5)

        lay.addWidget(QLabel("Alarm every:"))
        self._interval_group = QButtonGroup(self)
        for minutes, label in INTERVAL_OPTIONS:
            radio = QRadioButton(label)
            radio.setChecked(minutes == interval)
            self._interval_group.addButton(radio, minutes)
            lay.addWidget(radio)
        if self._interval_group.checkedId() < 0:
            fallback = self._interval_group.button(DEFAULT_INTERVAL)
            if fallback is not None:
                fallback.setChecked(True)

        hint = QLabel("Rings on the clock - 15 minutes means :00, :15, :30, :45.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFixedHeight(1)
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)

        lay.addWidget(QLabel("When it rings:"))
        self._mode_group = QButtonGroup(self)
        blink_rb = QRadioButton("Blink only")
        sound_rb = QRadioButton("Blink and sound")
        self._mode_group.addButton(blink_rb, 0)
        self._mode_group.addButton(sound_rb, 1)
        (sound_rb if mode == MODE_SOUND else blink_rb).setChecked(True)
        lay.addWidget(blink_rb)
        lay.addWidget(sound_rb)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self._file_lbl = QLabel()
        self._file_lbl.setObjectName("file")
        self._file_lbl.setMinimumWidth(190)
        file_row.addWidget(self._file_lbl, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse)
        file_row.addWidget(browse)
        lay.addLayout(file_row)
        self._refresh_file_label()

        ring = QLabel(f"Rings for {RING_SECONDS} seconds, or click the bulb to stop.")
        ring.setObjectName("hint")
        lay.addWidget(ring)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addSpacing(4)
        lay.addLayout(row)

    def _refresh_file_label(self) -> None:
        if self._sound_file:
            self._file_lbl.setText(os.path.basename(self._sound_file))
            self._file_lbl.setToolTip(self._sound_file)
        else:
            self._file_lbl.setText("Default beep")
            self._file_lbl.setToolTip("No file chosen - the system beep is used")

    def _on_browse(self) -> None:
        start = os.path.dirname(self._sound_file) if self._sound_file else ""
        path, _ = QFileDialog.getOpenFileName(self, "Choose alarm sound", start, SOUND_FILTER)
        if path:
            self._sound_file = path
            self._refresh_file_label()
            # choosing a file is a clear request to hear it
            btn = self._mode_group.button(1)
            if btn is not None:
                btn.setChecked(True)

    def selected_interval(self) -> int:
        checked = self._interval_group.checkedId()
        return checked if checked >= 0 else DEFAULT_INTERVAL

    def selected_mode(self) -> str:
        return MODE_SOUND if self._mode_group.checkedId() == 1 else MODE_BLINK

    def selected_sound(self) -> str:
        return self._sound_file
