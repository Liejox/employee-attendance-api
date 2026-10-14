# DECISIONS.md

1. **Indexes.** `employees.emp_code` (unique): no duplicate employees. `attendance_logs (emp_code, date)` (unique): one record per employee per day, the referee for the punch-in race, and per-employee queries. `attendance_logs (date -1, emp_code 1)`: month and date-range scans, and the list's sort. `employees (department, joined_on)`: headcount and trend. Rejected: `status`, only five values, so it filters poorly.

2. **Punch-in race.** Both requests call `insert_one`. The unique `(emp_code, date)` index lets one succeed; the other gets `DuplicateKeyError`, which becomes 409. No check-then-insert, so exactly one 201.

3. **Ties.** Standard competition rank (1, 1, 3) on total late minutes only. `rank <= limit` is applied after ranking, so everyone tied at the cutoff is returned and the list can exceed `limit`.

4. **Headcount.** It comes from `employees` (`joined_on` on or before month end), not from logs, and is merged with the log statistics, so employees without logs still count.

5. **100x data.** Summary and leaderboard group logs per employee before joining, but still read every log of the month. I would store monthly per-employee totals, updated on each punch and correction.
