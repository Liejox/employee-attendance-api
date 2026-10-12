from datetime import datetime, timezone

from app.main import (IST, attendance_date, compute_half_day, compute_late_minutes,
                      compute_overtime, compute_work_hours, round_half_up)


def ist(y, mo, d, h, mi, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=IST).astimezone(timezone.utc)


# R2 examples from the contract (shift 09:30)
D = "2026-07-06"
assert compute_late_minutes(ist(2026, 7, 6, 9, 40, 0), D, "09:30", "18:30") == 0
assert compute_late_minutes(ist(2026, 7, 6, 9, 40, 1), D, "09:30", "18:30") == 10
assert compute_late_minutes(ist(2026, 7, 6, 10, 15, 59), D, "09:30", "18:30") == 45
assert compute_late_minutes(ist(2026, 7, 6, 9, 0, 0), D, "09:30", "18:30") == 0
assert compute_late_minutes(ist(2026, 7, 6, 9, 40, 0, 900000), D, "09:30", "18:30") == 0
assert compute_late_minutes(ist(2026, 7, 6, 10, 5), D, "09:30", "18:30") == 35

# R3 overtime
assert compute_overtime(ist(2026, 7, 6, 18, 35), D, "09:30", "18:30") == 0
assert compute_overtime(ist(2026, 7, 6, 18, 59, 59), D, "09:30", "18:30") == 0
assert compute_overtime(ist(2026, 7, 6, 19, 0, 0), D, "09:30", "18:30") == 30
assert compute_overtime(ist(2026, 7, 6, 19, 10), D, "09:30", "18:30") == 40
assert compute_overtime(ist(2026, 7, 6, 17, 0), D, "09:30", "18:30") == 0

# R1 overnight 22:00-06:00
assert attendance_date(ist(2026, 7, 6, 21, 55), "22:00", "06:00") == "2026-07-06"
assert attendance_date(ist(2026, 7, 7, 1, 0), "22:00", "06:00") == "2026-07-06"
assert attendance_date(ist(2026, 7, 7, 5, 59, 59), "22:00", "06:00") == "2026-07-06"
assert attendance_date(ist(2026, 7, 7, 6, 0, 0), "22:00", "06:00") == "2026-07-07"
assert attendance_date(ist(2026, 7, 6, 9, 28), "09:30", "18:30") == "2026-07-06"
assert compute_overtime(ist(2026, 7, 7, 6, 40), "2026-07-06", "22:00", "06:00") == 40
assert compute_late_minutes(ist(2026, 7, 6, 21, 55), "2026-07-06", "22:00", "06:00") == 0
assert compute_late_minutes(ist(2026, 7, 7, 0, 30), "2026-07-06", "22:00", "06:00") == 150

# IST date, not UTC date: 00:30 IST on 7/7 is 19:00 UTC on 7/6
assert attendance_date(ist(2026, 7, 7, 0, 30), "09:30", "18:30") == "2026-07-07"

# R4 work hours and half-up
assert compute_work_hours(ist(2026, 7, 6, 9, 28), ist(2026, 7, 6, 18, 35)) == 9.12
assert compute_work_hours(ist(2026, 7, 7, 9, 30), ist(2026, 7, 7, 13, 0)) == 3.5
assert compute_work_hours(ist(2026, 7, 6, 21, 55), ist(2026, 7, 7, 6, 40)) == 8.75
assert compute_work_hours(ist(2026, 7, 6, 9, 0, 0), ist(2026, 7, 6, 9, 7, 30)) == 0.13
assert round(0.125, 2) == 0.12  # the starter's bug
assert round_half_up(2.675, 2) == 2.68

# R5 half day
assert compute_half_day(4.49) is True
assert compute_half_day(4.5) is False
assert compute_half_day(3.5) is True
assert compute_half_day(None) is False

print("ALL HELPER TESTS PASSED")