"""
Pillar F — Vietnamese context provider.

Provides time-of-day and Vietnamese holiday context that biases the
valence/arousal target in recommend_by_colors.

Usage:
    from core.vn_context import get_context_shift
    shift = get_context_shift()
    # {'valence_shift': +0.10, 'arousal_shift': +0.05, 'label': 'Tết Nguyên Đán'}
"""

from __future__ import annotations

import datetime
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Vietnamese holiday calendar (fixed and lunar approximations for 2025-2027)
# ---------------------------------------------------------------------------
# Format: (month, day) → {label, valence_shift, arousal_shift}
# Lunar holidays use the approximate Gregorian date for 2025-2027.
_FIXED_HOLIDAYS: list[tuple[int, int, Dict]] = [
    # Tết Dương lịch (New Year's Day) — fixed
    (1,  1,  {"label": "Tết Dương Lịch",   "valence_shift": +0.10, "arousal_shift": +0.05}),
    # Ngày Thống nhất
    (4,  30, {"label": "30 Tháng 4",        "valence_shift": +0.12, "arousal_shift": +0.08}),
    # Quốc tế Lao động
    (5,  1,  {"label": "1 Tháng 5",         "valence_shift": +0.08, "arousal_shift": +0.05}),
    # Quốc khánh
    (9,  2,  {"label": "Quốc Khánh 2/9",    "valence_shift": +0.12, "arousal_shift": +0.10}),
    # Giáng Sinh
    (12, 24, {"label": "Giáng Sinh Eve",    "valence_shift": +0.12, "arousal_shift": +0.05}),
    (12, 25, {"label": "Giáng Sinh",        "valence_shift": +0.15, "arousal_shift": +0.05}),
    (12, 31, {"label": "Giao Thừa Dương",   "valence_shift": +0.12, "arousal_shift": +0.08}),
    # Valentine
    (2,  14, {"label": "Valentine",         "valence_shift": +0.08, "arousal_shift": -0.05}),
    # Halloween
    (10, 31, {"label": "Halloween",         "valence_shift": -0.05, "arousal_shift": +0.10}),
]

# Approximate Gregorian dates for major lunar holidays 2025-2027
_LUNAR_HOLIDAYS: list[tuple[str, str, Dict]] = [
    # Tết Nguyên Đán 2026 (year of Horse — Feb 17)
    ("2026-02-17", "2026-02-23",
     {"label": "Tết Nguyên Đán", "valence_shift": +0.20, "arousal_shift": +0.10}),
    # Tết Nguyên Đán 2025 (Jan 29)
    ("2025-01-29", "2025-02-04",
     {"label": "Tết Nguyên Đán", "valence_shift": +0.20, "arousal_shift": +0.10}),
    # Tết Nguyên Đán 2027 (Feb 6)
    ("2027-02-06", "2027-02-12",
     {"label": "Tết Nguyên Đán", "valence_shift": +0.20, "arousal_shift": +0.10}),
    # Tết Trung Thu (Mid-Autumn) 2025 Oct 6
    ("2025-10-06", "2025-10-06",
     {"label": "Tết Trung Thu",  "valence_shift": +0.10, "arousal_shift": -0.05}),
    # Tết Trung Thu 2026 Sep 25
    ("2026-09-25", "2026-09-25",
     {"label": "Tết Trung Thu",  "valence_shift": +0.10, "arousal_shift": -0.05}),
]

# Time-of-day valence/arousal modifiers
_TIME_OF_DAY: list[tuple[int, int, Dict]] = [
    (5,  8,  {"label": "Sáng sớm",  "valence_shift": +0.05, "arousal_shift": -0.08}),
    (8,  12, {"label": "Buổi sáng", "valence_shift": +0.08, "arousal_shift": +0.05}),
    (12, 14, {"label": "Trưa",      "valence_shift": +0.03, "arousal_shift": 0.00}),
    (14, 18, {"label": "Chiều",     "valence_shift": 0.00,  "arousal_shift": +0.03}),
    (18, 21, {"label": "Tối",       "valence_shift": -0.03, "arousal_shift": -0.03}),
    (21, 24, {"label": "Đêm khuya", "valence_shift": -0.05, "arousal_shift": -0.10}),
    (0,  5,  {"label": "Nửa đêm",   "valence_shift": -0.08, "arousal_shift": -0.12}),
]


def _check_fixed_holiday(today: datetime.date) -> Optional[Dict]:
    for month, day, info in _FIXED_HOLIDAYS:
        if today.month == month and today.day == day:
            return dict(info)
    return None


def _check_lunar_holiday(today: datetime.date) -> Optional[Dict]:
    for start_str, end_str, info in _LUNAR_HOLIDAYS:
        start = datetime.date.fromisoformat(start_str)
        end   = datetime.date.fromisoformat(end_str)
        if start <= today <= end:
            return dict(info)
    return None


def _time_of_day_shift(hour: int) -> Dict:
    for start_h, end_h, info in _TIME_OF_DAY:
        if start_h <= hour < end_h:
            return dict(info)
    return {"label": "Đêm khuya", "valence_shift": -0.05, "arousal_shift": -0.10}


def get_context_shift(
    dt: Optional[datetime.datetime] = None,
    use_time: bool = True,
    use_holiday: bool = True,
) -> Dict:
    """Return combined valence/arousal shift for the current (or given) datetime.

    Returns:
        {
          "valence_shift": float,
          "arousal_shift": float,
          "label": str,         # human-readable context name
          "is_holiday": bool,
        }
    """
    if dt is None:
        dt = datetime.datetime.now()
    today = dt.date()
    hour  = dt.hour

    v_shift = 0.0
    a_shift = 0.0
    labels: list[str] = []
    is_holiday = False

    if use_holiday:
        h = _check_lunar_holiday(today) or _check_fixed_holiday(today)
        if h:
            v_shift += h["valence_shift"]
            a_shift += h["arousal_shift"]
            labels.append(h["label"])
            is_holiday = True

    if use_time:
        t = _time_of_day_shift(hour)
        v_shift += t["valence_shift"]
        a_shift += t["arousal_shift"]
        if t["label"] not in labels:
            labels.append(t["label"])

    return {
        "valence_shift": round(v_shift, 3),
        "arousal_shift": round(a_shift, 3),
        "label": " · ".join(labels) if labels else "Bình thường",
        "is_holiday": is_holiday,
    }
