# Employee Attendance & Analytics API

FastAPI + PyMongo on MongoDB. All the code is in `app/main.py`. Every endpoint in `openapi.yaml` is done: employees, punch-in, punch-out, attendance list, PATCH regularize, the four analytics endpoints and `/admin/explain`.

## Run (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a file called `.env` with two lines:

```
MONGO_URI=<your connection string>
MONGO_DB=attendance_db
```

Optional: `python sample_seed.py` loads the nine sample documents. Then start the server:

```
uvicorn app.main:app --port 8000
```

On Linux / macOS use `source .venv/bin/activate`. Open http://127.0.0.1:8000/docs to try it. Indexes are created at startup. It needs MongoDB 6.0+ (for `$setWindowFields` and `$densify`); Atlas M0 works. `.env` is not committed.

## Tests

`python test_helpers.py` checks the helper functions (late minutes, overtime, rounding, half day, overnight shifts). The endpoints I tested by hand on Atlas, with the sample data and with about 100k generated records. `/admin/explain` shows `IXSCAN` and no `COLLSCAN` for all five endpoints.

I used AI tools as a reference while working. I tested every endpoint myself and I can explain the code.

## Known limits

* No automated API tests in the repo, only `test_helpers.py`.
* If a PATCH or punch-out loses a race it gets 409 and the client has to retry. There is no automatic retry.
* The department summary and the late leaderboard read all logs of the month (40 to 100 ms for about 11,500 logs on Atlas M0). For much bigger data they need monthly roll-ups (DECISIONS.md, point 5).
* The 7-day moving average in the trend is the average of the already rounded daily rates, which is how I read the contract.
* Logs of an employee who joined after the month end still count in that department's sums, but not in its headcount.
