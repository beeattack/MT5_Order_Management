"""Wall-clock aligned interval scheduling for the alarm bulb.

The alarm fires on clock boundaries, not on elapsed time since it was armed:
a 5-minute interval rings at :00, :05, :10 ... regardless of when the app
started. Pure functions of a datetime so the behaviour is testable offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# Selectable intervals, in minutes. 0 means the alarm is off.
INTERVAL_OPTIONS: tuple[tuple[int, str], ...] = (
    (0,  "Off"),
    (5,  "5 minutes"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (60, "1 hour"),
)
DEFAULT_INTERVAL = 0

_MINUTES_PER_DAY = 24 * 60


def next_due(now: datetime, minutes: int) -> datetime | None:
    """First boundary strictly after *now* for an interval of *minutes*.

    Boundaries are counted from midnight, so 15 gives :00/:15/:30/:45 and 60
    gives the top of the hour. Returns None when the alarm is off.

    Landing exactly on a boundary returns the *next* one — the caller has just
    fired, and should not fire again for the same instant.
    """
    if minutes <= 0:
        return None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds() / 60.0
    steps = int(elapsed // minutes) + 1
    return midnight + timedelta(minutes=steps * minutes)
