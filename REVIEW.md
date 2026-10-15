# REVIEW.md

These are the problems I found in the starter `app/main.py`. Line numbers are from the starter file as it was given. I tried each one with an example before fixing it. R1 to R10 are the rules written in `openapi.yaml`.

| # | Where | What is wrong | How you would see it | How I fixed it |
|---|---|---|---|---|
| 1 | `compute_late_minutes` l.35 | Shift start is built on the punch-in's own date and time zone. Punch-ins are UTC, shifts are IST, so it is 5.5 hours off. Overnight shifts get the wrong day. | Shift 22:00-06:00, punch-in 01:05 IST. Starter gives 0, it should be 185. | `shift_bounds()` builds the start in IST on the attendance date. An overnight end goes to the next day. |
| 2 | `compute_late_minutes` l.36-37 | It cuts to whole minutes first, then checks `> 10`. 09:40:01 becomes 10, and `10 > 10` is false. | Shift 09:30, punch-in 09:40:01. Starter gives 0, it should be 10. | Check seconds `> 600` first, then take whole minutes since shift start. |
| 3 | all helpers | Seconds are never cut off (R1), so 09:40:00.900 is later than 09:40:00. | Punch-in 09:40:00.900 should be 0 late. | `trunc_seconds()` is used on every time before calculating, and the cut value is stored. |
| 4 | `compute_work_hours` l.41 | `round()` is not half-up (R4). | 450 seconds is 0.125 hours. Starter gives 0.12, it should be 0.13. | `Decimal(seconds) / 3600` with `ROUND_HALF_UP`. |
| 5 | `compute_overtime` l.47 | No 30-minute minimum (R3). Any extra minutes count. | Shift ends 18:30, punch-out 18:50. Starter gives 20, it should be 0. | Count only if it is 30 or more, otherwise 0. |
| 6 | `compute_overtime` l.46 | Shift end is always on the punch-out date, so an overnight shift end is wrong. It also mixes a time with zone and one without, which can crash. | Shift 22:00-06:00, punch-out 06:40 next day. Starter gives 1480, it should be 40. | Same `shift_bounds()`. All datetimes now carry a time zone. |
| 7 | helpers (missing) | There is no half-day rule (R5), so `half_day` is always false. | 4 h 29 m 59 s is not a half day. 4.48 h is. | `compute_half_day` on the rounded hours (`< 4.50`). |
| 8 | top of file l.22 | The Mongo client returns dates without a time zone, and has no timeout. | A wrong URI hangs for 30 seconds. | `tz_aware=True` and `serverSelectionTimeoutMS=5000`. |
| 9 | whole app | No indexes. Nothing stops duplicate `emp_code` or `(emp_code, date)`, and every query scans everything. | Duplicates when requests come in parallel. `COLLSCAN` in explain. | `ensure_indexes()` runs at startup (see DECISIONS.md). |
| 10 | `health` l.72 | It says ok even when MongoDB is down. | Use a wrong URI. `/health` still says ok. | It pings the database and returns 503 if that fails. |
| 11 | `create_employee` l.79-80 | It checks first and inserts after. Two parallel POSTs both pass the check. | Send the same POST twice at once. Two 201s, same `emp_code`. | Unique index on `emp_code`. `DuplicateKeyError` becomes 409. |
| 12 | `EmployeeIn` l.53-60 | No validation at all. | Empty name, bad email, `25:99`, `2026-02-30`, same start and end shift all return 201. | Pattern and length checks, a real-date check, shifts must differ. All give 422. |
| 13 | `create_employee` l.82 | `created_at` uses local server time and is returned as a datetime. | The value changes with the server's time zone. | Saved in UTC. Returned as epoch milliseconds. |
| 14 | `list_employees` l.93 | `skip = page * page_size` skips the first page. | `page=1` gives an empty list. | `(page - 1) * page_size`. |
| 15 | `list_employees` l.94 | `total` counts all employees and ignores the department filter (R10). | `?department=Sales` shows everyone in total. | `count_documents(q)` with the same filter as the list. |
| 16 | `list_employees` l.89 | `page` and `page_size` are not checked, and there is no sort. | `page=0` works. The same row can appear on two pages. | `page >= 1`, `page_size` 1 to 100, sorted by `emp_code`. |
| 17 | `punch_in` l.101-113 | Unknown employee: `find_one` gives `None` and the next line crashes. | `{"emp_code": "EMP9999"}` gives 500. | Return 404. |
| 18 | `punch_in` l.102 | The timestamp uses the server's local zone. Value 0 is treated as missing. Seconds, floats and strings are accepted. | `punched_at = 1760000000` (that is seconds) is accepted as a date in 1970. | Strict integer in a valid millisecond range, converted to UTC, `is not None`, seconds cut off. |
| 19 | `punch_in` l.103 | The date is the server's date, not the IST date, and the overnight rule is ignored (R1). | A 22:00-06:00 employee punching at 01:05 IST should get the previous day. | `attendance_date()`. |
| 20 | `punch_in` l.104-118 | Check first, insert after. Parallel punch-ins all pass the check. | 8 identical requests at once give several 201s and duplicate records. | Unique `(emp_code, date)` index. `DuplicateKeyError` becomes 409. Only one gets 201. |
| 21 | `PunchInIn` l.66 | `status` accepts any text. | `{"status": "LEAVE"}` returns 201. | Only `PRESENT`, `WFH` or `ON_DUTY`. Anything else is 422. |
| 22 | `punch_in` l.119-121 | The response shows the Mongo `id` and a datetime instead of epoch milliseconds. | Look at the 201 response. | The response is built by `attendance_out()`. |
| 23 | `list_attendance` l.144-147 | It loads every matching record into Python, then sorts and slices there. | With 100k records every request is slow. | `find().sort().skip().limit()` in MongoDB, and `count_documents()`. |
| 24 | `list_attendance` l.145 | Sorts by date only. The contract says date descending, then `emp_code` ascending. | Several people on one date come in random order. | `sort([("date", -1), ("emp_code", 1)])`, the same order as the index. |
| 25 | `list_attendance` l.126-131 | Nothing is checked. | `date_from` after `date_to`, a date like `2026-02-30`, a wrong status or `page=0` all go through. | `DateStr`, `Status`, `Query(ge/le)`, and 422 if `date_from` is after `date_to`. |
| 26 | `list_attendance` l.148-149 | Shows `id` and datetimes. Records without `half_day` or `history` look different. | Compare the output with the contract. | `attendance_out()` fills the missing fields with defaults. |
| 27 | missing endpoints | punch-out, PATCH, the four analytics endpoints and `/admin/explain` do not exist. | They give 404. | I built them. Punch-out and PATCH update only if the record is still unchanged, so a parallel request gets 409. |

## Checked and fine

* **`date` saved as `YYYY-MM-DD` text.** This format sorts correctly as text, so range queries and indexes work. Kept.
* **`IST = timezone(timedelta(hours=5, minutes=30))`.** Correct for India. No daylight saving.
* **`history: []` and `overtime_minutes: 0` on punch-in.** Correct. History is only for corrections, and overtime is known only at punch-out.
* **`load_dotenv()` with `MONGO_URI` and `MONGO_DB`.** Fine, and no secret is in the code.
* **`punch_in` and `punch_out` saved as dates in Mongo.** Correct. Only the API turns them into milliseconds.
* **409 for a second punch-in on the same date.** Matches the contract. I only changed how it is detected (unique index instead of a read).
