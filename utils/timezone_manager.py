from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _ZONEINFO_AVAILABLE = True
except ImportError:
    ZoneInfo = None  # type: ignore[assignment,misc]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]
    _ZONEINFO_AVAILABLE = False

# Curated list relevant for forex/CFD traders: (display_label, IANA_name)
TIMEZONE_OPTIONS: list[tuple[str, str]] = [
    ("UTC",                          "UTC"),
    ("UTC+0   London (GMT/BST)",     "Europe/London"),
    ("UTC+1   Berlin / Paris",       "Europe/Paris"),
    ("UTC+2   Helsinki / Athens",    "Europe/Helsinki"),
    ("UTC+3   Moscow",               "Europe/Moscow"),
    ("UTC+3   Riyadh",               "Asia/Riyadh"),
    ("UTC+4   Dubai",                "Asia/Dubai"),
    ("UTC+5   Karachi",              "Asia/Karachi"),
    ("UTC+5:30 Mumbai / Delhi",      "Asia/Kolkata"),
    ("UTC+6   Dhaka",                "Asia/Dhaka"),
    ("UTC+7   Bangkok / Jakarta",    "Asia/Bangkok"),
    ("UTC+8   Singapore / KL",       "Asia/Singapore"),
    ("UTC+8   Beijing / Hong Kong",  "Asia/Shanghai"),
    ("UTC+9   Tokyo / Seoul",        "Asia/Tokyo"),
    ("UTC+10  Sydney (AEST/AEDT)",   "Australia/Sydney"),
    ("UTC+12  Auckland",             "Pacific/Auckland"),
    ("UTC-5   New York (EST/EDT)",   "America/New_York"),
    ("UTC-6   Chicago (CST/CDT)",    "America/Chicago"),
    ("UTC-7   Denver (MST/MDT)",     "America/Denver"),
    ("UTC-8   Los Angeles (PST/PDT)","America/Los_Angeles"),
]

DEFAULT_TZ = "UTC"


def convert_dt(dt: datetime, tz_name: str) -> datetime:
    """Convert a UTC-aware (or naive-UTC) datetime to the given IANA timezone."""
    if not _ZONEINFO_AVAILABLE:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        return dt


def localize_naive(dt: datetime, tz_name: str) -> datetime:
    """Attach tz_name to a naive datetime (treats the naive value as being in that timezone)."""
    if dt.tzinfo is not None:
        return dt
    if not _ZONEINFO_AVAILABLE or tz_name == "UTC":
        return dt.replace(tzinfo=timezone.utc)
    try:
        return dt.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


def format_dt(dt: datetime, tz_name: str) -> str:
    """Convert UTC-aware dt to tz_name and return 'YYYY-MM-DD HH:MM TZ'."""
    local = convert_dt(dt, tz_name)
    return local.strftime("%Y-%m-%d %H:%M %Z")
