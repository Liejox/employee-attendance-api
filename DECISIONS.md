# DECISIONS.md

1. Indexes. I made four. employees.emp_code is unique, so there are no duplicate employees. attendance_logs (emp_code, date) is unique: one record per person per day, and it also settles the punch-in race. attendance_logs (date -1, emp_code 1) serves month and date-range queries and the list sort. employees (department, joined_on) is for headcount and the trend. I did not index status because it has only five values.

2. Two identical punch-ins. Both requests just call insert_one. The unique (emp_code, date) index lets only one of them in. The other gets DuplicateKeyError and I return 409. There is no check first, so no gap for a race.

3. Ties at the cutoff. Ties share a rank and the next rank is skipped (1, 1, 3). I apply rank <= limit after ranking, so everyone tied at the cutoff is returned and the list can be longer than limit.

4. Employees with no logs. Headcount comes from the employees collection (joined_on on or before the month end), not from the logs. I merge it with the log numbers, so they still count, with zeros.

5. 100 times the data. The summary and the leaderboard still read every log of the month. I would keep monthly totals per employee and update them on every punch and correction.
