"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

def ensure_indexes():
    """Create indexes at startup. create_index is idempotent (safe to run every time)."""
    db.employees.create_index("emp_code", unique=True)
    db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
    db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    yield


app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def to_ms(dt):
    """Mongo datetime (UTC) -> epoch milliseconds (int). None stays None."""
    if dt is None:
        return None
    return (dt - EPOCH) // timedelta(milliseconds=1)


def from_ms(ms: int) -> datetime:
    """epoch milliseconds (int) -> UTC datetime."""
    return EPOCH + timedelta(milliseconds=ms)


def employee_out(doc: dict) -> dict:
    """Employee document -> API shape (no _id, created_at in ms)."""
    doc = dict(doc)
    doc.pop("_id", None)
    doc["created_at"] = to_ms(doc.get("created_at"))
    return doc


def round_half_up(value, places: int = 2) -> float:
    """Round half-up: 0.125 -> 0.13. Python's round() is banker's/float based."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def trunc_seconds(dt: datetime) -> datetime:
    """R1: drop microseconds, keep whole seconds."""
    return dt.replace(microsecond=0)


def parse_hhmm(value: str):
    h, m = value.split(":")
    return int(h), int(m)


def is_overnight(shift_start: str, shift_end: str) -> bool:
    return shift_end <= shift_start


def attendance_date(punch_in: datetime, shift_start: str, shift_end: str) -> str:
    """R1: IST calendar date of the punch-in; overnight early punch -> previous day."""
    local = punch_in.astimezone(IST)
    day = local.date()
    if is_overnight(shift_start, shift_end):
        eh, em = parse_hhmm(shift_end)
        if (local.hour, local.minute) < (eh, em):
            day -= timedelta(days=1)
    return day.isoformat()


def shift_bounds(date_str: str, shift_start: str, shift_end: str):
    """IST start and end datetimes of the shift that belongs to attendance date."""
    sh, sm = parse_hhmm(shift_start)
    eh, em = parse_hhmm(shift_end)
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)
    start = day.replace(hour=sh, minute=sm)
    end = day.replace(hour=eh, minute=em)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def compute_late_minutes(punch_in: datetime, date_str: str, shift_start: str, shift_end: str) -> int:
    """R2: late only if strictly more than 10:00 after shift start; then floor minutes since start."""
    start, _ = shift_bounds(date_str, shift_start, shift_end)
    seconds = int((trunc_seconds(punch_in) - start).total_seconds())
    return seconds // 60 if seconds > 600 else 0


def compute_overtime(punch_out: datetime, date_str: str, shift_start: str, shift_end: str) -> int:
    """R3: floor minutes after shift end, counted only when at least 30."""
    _, end = shift_bounds(date_str, shift_start, shift_end)
    minutes = int((trunc_seconds(punch_out) - end).total_seconds()) // 60
    return minutes if minutes >= 30 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    """R4: seconds / 3600, 2 decimals half-up."""
    seconds = int((trunc_seconds(punch_out) - trunc_seconds(punch_in)).total_seconds())
    return round_half_up(Decimal(seconds) / Decimal(3600), 2)


def compute_half_day(work_hours) -> bool:
    """R5: rounded work_hours < 4.50 (None when not punched out yet)."""
    return work_hours is not None and work_hours < 4.50

def history_out(entry: dict) -> dict:
    """History entry: Mongo datetimes -> epoch ms (also inside changes.punch_in / punch_out)."""
    changes = {}
    for field, change in entry.get("changes", {}).items():
        if field in ("punch_in", "punch_out"):
            changes[field] = {"from": to_ms(change.get("from")), "to": to_ms(change.get("to"))}
        else:
            changes[field] = {"from": change.get("from"), "to": change.get("to")}
    return {"at": to_ms(entry.get("at")), "by": entry.get("by"), "reason": entry.get("reason"), "changes": changes}


def attendance_out(doc: dict) -> dict:
    """Attendance document -> API shape. No _id, instants in ms, missing fields get defaults."""
    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": to_ms(doc.get("punch_in")),
        "punch_out": to_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": [history_out(h) for h in doc.get("history", [])],
    }


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
EpochMs = Annotated[int, Field(strict=True, ge=100_000_000_000, le=4_102_444_800_000)]

def _valid_date(v: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v):
        raise ValueError("must be YYYY-MM-DD")
    datetime.strptime(v, "%Y-%m-%d")  # rejects 2026-02-30
    return v


DateStr = Annotated[str, AfterValidator(_valid_date)]
Status = Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]


class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=HHMM)
    shift_end: str = Field("18:30", pattern=HHMM)
    joined_on: str

    @field_validator("joined_on")
    @classmethod
    def joined_on_is_a_real_date(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v):
            raise ValueError("joined_on must be YYYY-MM-DD")
        datetime.strptime(v, "%Y-%m-%d")  # raises ValueError for 2026-02-30
        return v

    @model_validator(mode="after")
    def shifts_must_differ(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[EpochMs] = None
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"

class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[EpochMs] = None


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except Exception:
        raise HTTPException(503, "MongoDB unavailable")
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return employee_out(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    cursor = db.employees.find(q).sort("emp_code", 1).skip(skip).limit(page_size)
    items = [employee_out(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(404, "employee not found")
    now = datetime.now(timezone.utc)
    ts = trunc_seconds(from_ms(body.punched_at) if body.punched_at is not None else now)
    d = attendance_date(ts, emp["shift_start"], emp["shift_end"])
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, d, emp["shift_start"], emp["shift_end"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    return attendance_out(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(404, "employee not found")
    ts = trunc_seconds(from_ms(body.punched_at) if body.punched_at is not None else datetime.now(timezone.utc))
    rec = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": ts}}, sort=[("punch_in", -1)]
    )
    if rec is None:
        raise HTTPException(404, "no punch-in found")
    if rec.get("punch_out") is not None:
        raise HTTPException(409, "already punched out")
    punch_in_ts = trunc_seconds(rec["punch_in"])
    if ts <= punch_in_ts or ts > punch_in_ts + timedelta(hours=24):
        raise HTTPException(422, "punched_at must be after punch_in and within 24 hours")
    work_hours = compute_work_hours(punch_in_ts, ts)
    updated = db.attendance_logs.find_one_and_update(
        {"_id": rec["_id"], "punch_out": None},
        {"$set": {
            "punch_out": ts,
            "work_hours": work_hours,
            "overtime_minutes": compute_overtime(ts, rec["date"], emp["shift_start"], emp["shift_end"]),
            "half_day": compute_half_day(work_hours),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(409, "already punched out")
    return attendance_out(updated)


def attendance_filter(emp_code, date_from, date_to, status) -> dict:
    """Builds the Mongo filter for GET /attendance (the explain endpoint reuses this)."""
    q = {}
    if emp_code is not None:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status is not None:
        q["status"] = status
    return q


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[DateStr] = None,
    date_to: Optional[DateStr] = None,
    status: Optional[Status] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must not be after date_to")
    q = attendance_filter(emp_code, date_from, date_to, status)
    total = db.attendance_logs.count_documents(q)
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [attendance_out(d) for d in cursor], "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
