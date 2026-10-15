# REVIEW.md

Problems I found in the starter `app/main.py`. Line numbers are from the starter as it was given. I ran each one or tested it before fixing it. R1-R10 are the rules in `openapi.yaml`.

| # | Where | What is wrong | How you would notice | How I fixed it |
|---|---|---|---|---|
| 1 | `compute_late_minutes`, l.35 | `punch_in.replace(hour, minute)` puts the shift start on the punch-in's own date and time zone. Punch-ins are UTC but shifts are IST, so it is 5.5 h off, and overnight shifts land on the wrong day. | Shift 22:00-06:00, punch-in 01:05 IST: starter gives 0, correct is 185. | New `shift_bounds()` builds the start in IST on the attendance date; an overnight end goes to the next day. |
| 2 | `compute_late_minutes`, l.36-37 | Seconds are cut to whole minutes before the grace check. 09:40:01 becomes 10 and `10 > 10` is false, so a late punch counts as on time. | Shift 09:30, punch-in 09:40:01: starter 0, correct 10. 10:15:59 should be 45. | Compare seconds `> 600`, then take whole minutes since shift start. |
| 3 | all helpers | Seconds are never truncated (R1), so 09:40:00.900 counts as later than 09:40:00. | Punch-in 09:40:00.900 should be 0. | `trunc_seconds()` on every instant before any calculation; the truncated value is stored. |
| 4 | `compute_work_hours`, l.41 | `round()` on a float is banker's rounding, not half-up (R4). | 450 s = 0.125 h: starter 0.12, should be 0.13. | `Decimal(seconds) / 3600` with `ROUND_HALF_UP`. |
| 5 | `compute_overtime`, l.47 | No 30-minute minimum (R3). Any positive minutes count. | Punch-out 18:50, shift end 18:30: starter 20, should be 0. | Whole minutes, only if `>= 30`, else 0. |
| 6 | `compute_overtime`, l.46 | Shift end is always on the punch date, so an overnight end is wrong. It also subtracts a naive `punch_out` from an IST-aware end, which can raise `TypeError`. | Shift 22:00-06:00, punch-out 06:40 next day: starter 1480, correct 40. | Same `shift_bounds()`, and every datetime is timezone-aware. |
| 7 | helpers (missing) | There is no half-day rule (R5), so `half_day` is always false. | 4 h 29 m 59 s rounds to 4.50 and is not a half day; 4.48 h is. | `compute_half_day` on the rounded `work_hours` (`< 4.50`). |
| 8 | module top, l.22 | `MongoClient` is not `tz_aware`, so dates come back naive. No timeout, so a bad URI hangs for 30 s. | Times shift by the server's offset; startup hangs if Atlas is unreachable. | `tz_aware=True` and `serverSelectionTimeoutMS=5000`. |
| 9 | whole app | No indexes. Nothing stops duplicate `emp_code` or `(emp_code, date)`, and every query scans the collection. | Duplicates under parallel requests; `COLLSCAN` in explain. | `ensure_indexes()` at startup (see DECISIONS.md). |
| 10 | `health`, l.72 | Always says ok, even if MongoDB is down. | Break the URI: `/health` still says ok. | Ping the database, return 503 on failure. |
| 11 | `create_employee`, l.79-80 | Check-then-insert race: two parallel POSTs both pass `find_one` and both insert. | Same POST twice at once: two 201s, duplicate `emp_code`. | Unique index on `emp_code`; `DuplicateKeyError` becomes 409. |
| 12 | `EmployeeIn`, l.53-60 | No validation. Empty name, bad email, `25:99`, `2026-02-30`, same shift start and end are all accepted. | POST any of those: 201. | Patterns and lengths, a real-date check, shifts must differ; all give 422. |
| 13 | `create_employee`, l.82 | `created_at = datetime.now()` is naive local time and returned as a datetime, not epoch ms. | Value depends on the server's time zone. | Stored in UTC, returned as epoch ms by `employee_out`. |
| 14 | `list_employees`, l.93 | `skip = page * page_size` skips the first page. | `page=1` returns an empty list. | `(page - 1) * page_size`. |
| 15 | `list_employees`, l.94 | `total` is `count_documents({})`, so it ignores the department filter (R10). | `?department=Sales`: total counts everyone. | `count_documents(q)` with the same filter. |
| 16 | `list_employees`, l.89 | `page` and `page_size` are not validated (0, negative, 10000) and there is no sort, so pages can overlap. | `page=0`; the same row on two pages. | `Query(ge=1)`, `page_size` max 100, sort by `emp_code`. |
| 17 | `punch_in`, l.101-113 | Unknown `emp_code`: `find_one` gives `None`, then `emp["shift_start"]` fails, so 500 instead of 404. | `{"emp_code": "EMP9999"}`. | Explicit 404. |
| 18 | `punch_in`, l.102 | `fromtimestamp(ms/1000)` uses the server's local zone. `if body.punched_at` treats 0 as missing. Seconds are not truncated. Seconds-looking, float and string values are accepted. | `punched_at = 1760000000` (seconds) is accepted as a 1970 date. | `EpochMs` strict int in a sane range, `from_ms()` to UTC, `is not None`, `trunc_seconds()`. |
| 19 | `punch_in`, l.103 | The date comes from the server clock, not the IST date, and ignores the overnight rule (R1). | 22:00-06:00 employee punching in at 01:05 IST belongs to the previous day. | `attendance_date(ts, shift_start, shift_end)`. |
| 20 | `punch_in`, l.104-118 | Check-then-insert race again: parallel punch-ins all pass the check and all insert. | 8 identical requests at once: several 201s, duplicate `(emp_code, date)`. | Unique `(emp_code, date)` index; `DuplicateKeyError` becomes 409. Exactly one 201. |
| 21 | `PunchInIn`, l.66 | `status: str` accepts anything (`LEAVE`, `ABSENT`, `"banana"`). Punch-in should only make PRESENT, WFH or ON_DUTY. | `{"status": "LEAVE"}` returns 201. | `Literal["PRESENT", "WFH", "ON_DUTY"]`, 422 otherwise. |
| 22 | `punch_in`, l.119-121 | The response leaks the Mongo id as `id` and gives `punch_in` as a datetime, not epoch ms. | Look at the 201 body. | Response built by `attendance_out()`. |
| 23 | `list_attendance`, l.144-147 | Loads all matching documents into Python, then sorts and slices there. Slow and heavy at 100k records. | 100k rows: seconds per request. | `find().sort().skip().limit()` in MongoDB and `count_documents()`. |
| 24 | `list_attendance`, l.145 | Sorts by date only. The contract says date descending, then `emp_code` ascending. | Several employees on one date come back in random order. | `sort([("date", -1), ("emp_code", 1)])`, the same order as the index. |
| 25 | `list_attendance`, l.126-131 | No validation: `date_from > date_to`, bad dates, unknown `status`, `page=0`, huge `page_size`. | Any of those inputs. | `DateStr`, `Status` literal, `Query(ge/le)`, 422 if `date_from > date_to`. |
| 26 | `list_attendance`, l.148-149 | Leaks `id`, gives datetimes instead of ms, and records without `half_day` or `history` look inconsistent. | Compare the output with the contract. | `attendance_out()` with defaults for missing fields. |
| 27 | missing endpoints | punch-out, PATCH, the four analytics endpoints and `/admin/explain` do not exist. | 404 on all of them. | Built them. Punch-out and PATCH use a conditional `find_one_and_update`, so a parallel request gets 409. |

## Checked and fine

* **`date` stored as a `YYYY-MM-DD` string.** ISO dates sort correctly as text, so `$gte` / `$lte` and index range scans work. Kept it.
* **`IST = timezone(timedelta(hours=5, minutes=30))`.** Right for India, no daylight saving.
* **`history: []` and `overtime_minutes: 0` on punch-in.** Correct: punch-in never writes history and overtime is only known at punch-out.
* **`load_dotenv()` with `MONGO_URI` / `MONGO_DB`.** Fine for local use, and no secret is in the code.
* **`punch_in` / `punch_out` stored as BSON dates.** Correct. Only the API converts to epoch ms.
* **409 for a second punch-in on the same date.** Matches the contract. I only changed how it is detected (unique index instead of a read).
