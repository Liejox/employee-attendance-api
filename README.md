# Employee Attendance & Analytics API

FastAPI + PyMongo service on MongoDB. All code is in `app/main.py`. Every endpoint in `openapi.yaml` is implemented: employees, punch-in / punch-out, attendance list, regularization (PATCH), the four analytics endpoints and `/admin/explain`.

## Run (Windows)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
(create a file named .env with two lines: MONGO_URI=<your connection string> and MONGO_DB=attendance_db)
python sample_seed.py       (optional: loads the nine sample documents)
uvicorn app.main:app --port 8000
```
On Linux / macOS use `source .venv/bin/activate`. Open http://127.0.0.1:8000/docs. Indexes are created automatically at startup. MongoDB 6.0 or newer is required (`$setWindowFields`, `$densify`); Atlas M0 works. Secrets stay in `.env`, which is not committed.

## Tests
`python test_helpers.py` checks the pure helpers (late minutes, overtime, half-up rounding, half-day edges, overnight shifts) with the examples from the rules. The endpoints were checked by hand against Atlas (sample data and a generated ~100k-record dataset) and `/admin/explain` shows `IXSCAN` and no `COLLSCAN` for all five endpoints.

## What is missing / known limits
* There is no automated API test suite in the repo; the helper tests above are the only committed tests.
* Concurrency losers on PATCH and punch-out get 409 and must retry; there is no automatic retry.
* The department summary and the late leaderboard still read every log of the requested month (about 40 to 100 ms for ~11,500 logs on Atlas M0); at much larger sizes they need monthly roll-ups (see DECISIONS.md, point 5).
* The trend's 7-day moving average is the mean of the already rounded daily rates, a literal reading of the contract.
* Logs of an employee who joined after the month end still count in that department's sums, but not in its headcount.
