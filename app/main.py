

"""

Employee Attendance & Analytics API

Version: 2.0.0



Run:

    uvicorn app.main:app --port 8000 --reload



Environment:

    MONGO_URI=mongodb://localhost:27017

    MONGO_DB=attendance_db

"""



import os

import re

import calendar

from contextlib import asynccontextmanager

from datetime import date, datetime, time, timedelta, timezone

from decimal import Decimal, ROUND_HALF_UP

from typing import Optional, Literal



from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query

from pydantic import (

    BaseModel,

    ConfigDict,

    StrictInt,

    field_validator,

    model_validator,

)

from pymongo import MongoClient, ReturnDocument

from pymongo.errors import DuplicateKeyError

from pymongo.collation import Collation



load_dotenv()



IST = timezone(timedelta(hours=5, minutes=30))

MIN_EPOCH_MS = 100_000_000_000

MAX_EPOCH_MS = 4_102_444_800_000



STATUSES = {"PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"}

PRESENCE_STATUSES = {"PRESENT", "WFH", "ON_DUTY"}



client = MongoClient(

    os.getenv("MONGO_URI", "mongodb://localhost:27017"),

    serverSelectionTimeoutMS=5000,

)

db = client[os.getenv("MONGO_DB", "attendance_db")]

employees_collection = db.employees

attendance_collection = db.attendance_logs





# -------------------- Application lifecycle --------------------



@asynccontextmanager

async def lifespan(app: FastAPI):

    db.command("ping")



    db.employees.create_index(

        [("emp_code", 1)],

        unique=True,

        name="uq_employees_emp_code",

    )



    db.attendance_logs.create_index(

        [("emp_code", 1), ("date", 1)],

        unique=True,

        name="uq_attendance_emp_code_date",

    )



    db.employees.create_index(

        [("department", 1), ("emp_code", 1)],

        name="ix_employees_department_emp_code",

    )



    db.employees.create_index(

        [("joined_on", 1), ("department", 1)],

        name="ix_employees_joined_department",

    )



    db.attendance_logs.create_index(

        [("date", -1), ("emp_code", 1)],

        name="ix_attendance_date_emp_code",

    )



    db.attendance_logs.create_index(

        [("emp_code", 1), ("punch_in", -1)],

        name="ix_attendance_emp_punch_in",

    )



    db.attendance_logs.create_index(

        [("status", 1), ("date", 1), ("emp_code", 1)],

        name="ix_attendance_status_date_emp",

    )



    yield

    client.close()





app = FastAPI(

    title="Employee Attendance & Analytics API",

    version="2.0.0",

    lifespan=lifespan,

)





# -------------------- Common validation helpers --------------------



def validate_iso_date(value: str, field_name: str = "date") -> date:

    try:

        parsed = date.fromisoformat(value)

    except (ValueError, TypeError):

        raise HTTPException(

            status_code=422,

            detail=f"{field_name} must use YYYY-MM-DD format",

        )



    if parsed.isoformat() != value:

        raise HTTPException(

            status_code=422,

            detail=f"{field_name} must use YYYY-MM-DD format",

        )



    return parsed





def validate_month(value: str) -> tuple[date, date]:

    if not re.fullmatch(r"\d{4}-\d{2}", value):

        raise HTTPException(

            status_code=422,

            detail="month must use YYYY-MM format",

        )



    try:

        year, month = map(int, value.split("-"))

        start = date(year, month, 1)

    except ValueError:

        raise HTTPException(

            status_code=422,

            detail="month must be a valid YYYY-MM month",

        )



    last_day = calendar.monthrange(year, month)[1]

    return start, date(year, month, last_day)





def epoch_ms_to_ist(value: Optional[int]) -> datetime:

    if value is None:

        return datetime.now(IST).replace(

            tzinfo=None,

            microsecond=0,

        )



    # StrictInt rejects floats and numeric strings in request models.

    if not MIN_EPOCH_MS <= value <= MAX_EPOCH_MS:

        raise HTTPException(

            status_code=422,

            detail="Timestamp must be valid epoch milliseconds",

        )



    return datetime.fromtimestamp(

        value / 1000,

        tz=timezone.utc,

    ).astimezone(IST).replace(

        tzinfo=None,

        microsecond=0,

    )





def truncate_to_seconds(value: datetime) -> datetime:

    return value.replace(microsecond=0)





def round_decimal(value, places: int = 2) -> float:

    quantum = Decimal("1").scaleb(-places)

    return float(

        Decimal(str(value)).quantize(

            quantum,

            rounding=ROUND_HALF_UP,

        )

    )





def serialize_document(document: dict) -> dict:

    document = dict(document)

    document.pop("_id", None)

    document.pop("id", None)

    return serialize_value(document)





def serialize_value(value):

    """Convert nested MongoDB values into JSON-friendly epoch-millisecond values."""

    if isinstance(value, datetime):

        if value.tzinfo is None:

            value = value.replace(tzinfo=timezone.utc)

        else:

            value = value.astimezone(timezone.utc)

        return int(value.timestamp() * 1000)



    if isinstance(value, dict):

        return {

            key: serialize_value(item)

            for key, item in value.items()

            if key not in {"_id", "id"}

        }



    if isinstance(value, list):

        return [serialize_value(item) for item in value]



    return value





# -------------------- Shift and attendance calculations --------------------



def shift_start_datetime(

    attendance_date: str,

    shift_start: str,

) -> datetime:

    hour, minute = map(int, shift_start.split(":"))

    base = datetime.fromisoformat(attendance_date)

    return base.replace(

        hour=hour,

        minute=minute,

        second=0,

        microsecond=0,

    )





def shift_end_datetime(

    attendance_date: str,

    shift_start: str,

    shift_end: str,

) -> datetime:

    start = shift_start_datetime(attendance_date, shift_start)

    end_hour, end_minute = map(int, shift_end.split(":"))



    end = start.replace(

        hour=end_hour,

        minute=end_minute,

    )



    if end <= start:

        end += timedelta(days=1)



    return end





def attendance_date_for_punch(

    punch_in: datetime,

    shift_start: str,

    shift_end: str,

) -> str:

    """

    Determine the shift-start calendar date.



    For an overnight shift such as 22:00â€“06:00, a punch-in

    between midnight and 05:59 belongs to the previous

    calendar day's shift.

    """

    if shift_end <= shift_start:

        end_hour, end_minute = map(int, shift_end.split(":"))

        local_time = (

            punch_in.hour,

            punch_in.minute,

        )



        if local_time < (end_hour, end_minute):

            return (punch_in.date() - timedelta(days=1)).isoformat()



    return punch_in.date().isoformat()





def compute_late_minutes(

    punch_in: datetime,

    shift_start: str,

    attendance_date: Optional[str] = None,

) -> int:

    """

    Apply the 10-minute grace rule.



    Arrival at exactly 10 minutes after shift start is not late.

    Once late, report floor minutes elapsed since shift start.

    """

    if attendance_date is None:

        attendance_date = punch_in.date().isoformat()



    start = shift_start_datetime(attendance_date, shift_start)

    elapsed_seconds = int((punch_in - start).total_seconds())



    if elapsed_seconds <= 600:

        return 0



    return elapsed_seconds // 60





def compute_work_hours(

    punch_in: datetime,

    punch_out: datetime,

) -> float:

    elapsed_seconds = Decimal(

        str((punch_out - punch_in).total_seconds())

    )

    hours = elapsed_seconds / Decimal("3600")



    return float(

        hours.quantize(

            Decimal("0.01"),

            rounding=ROUND_HALF_UP,

        )

    )





def compute_overtime(

    punch_out: datetime,

    shift_start: str,

    shift_end: str,

    attendance_date: str,

) -> int:

    end = shift_end_datetime(

        attendance_date,

        shift_start,

        shift_end,

    )



    overtime_minutes = int(

        (punch_out - end).total_seconds()

    ) // 60



    return overtime_minutes if overtime_minutes >= 30 else 0





def derive_attendance_fields(

    *,

    status: str,

    punch_in: Optional[datetime],

    punch_out: Optional[datetime],

    employee: dict,

    attendance_date: str,

) -> dict:

    """Calculate server-owned metrics from source attendance fields."""

    if status in {"ABSENT", "LEAVE"}:

        return {

            "punch_in": None,

            "punch_out": None,

            "work_hours": 0,

            "late_minutes": 0,

            "overtime_minutes": 0,

            "half_day": False,

        }



    if punch_in is None:

        raise HTTPException(

            status_code=422,

            detail="Presence statuses require punch_in",

        )



    late_minutes = compute_late_minutes(

        punch_in,

        employee["shift_start"],

        attendance_date,

    )



    if punch_out is None:

        return {

            "punch_in": punch_in,

            "punch_out": None,

            "work_hours": None,

            "late_minutes": late_minutes,

            "overtime_minutes": 0,

            "half_day": False,

        }



    if punch_out <= punch_in:

        raise HTTPException(

            status_code=422,

            detail="punch_out must be after punch_in",

        )



    if punch_out > punch_in + timedelta(hours=24):

        raise HTTPException(

            status_code=422,

            detail="punch_out cannot be more than 24 hours after punch_in",

        )



    work_hours = compute_work_hours(punch_in, punch_out)



    return {

        "punch_in": punch_in,

        "punch_out": punch_out,

        "work_hours": work_hours,

        "late_minutes": late_minutes,

        "overtime_minutes": compute_overtime(

            punch_out,

            employee["shift_start"],

            employee["shift_end"],

            attendance_date,

        ),

        "half_day": work_hours < 4.50,

    }





def is_weekday(value: date) -> bool:

    return value.weekday() < 5





# -------------------- Request models --------------------



class EmployeeIn(BaseModel):

    model_config = ConfigDict(

        str_strip_whitespace=True,

        extra="forbid",

    )



    emp_code: str

    name: str

    email: str

    department: str

    shift_start: str = "09:30"

    shift_end: str = "18:30"

    joined_on: str



    @field_validator("emp_code")

    @classmethod

    def validate_emp_code(cls, value: str) -> str:

        if not re.fullmatch(r"EMP\d{4,6}", value):

            raise ValueError(

                "emp_code must match EMP followed by 4 to 6 digits"

            )

        return value



    @field_validator("name")

    @classmethod

    def validate_name(cls, value: str) -> str:

        if not 1 <= len(value) <= 100:

            raise ValueError(

                "name must contain 1 to 100 characters"

            )

        return value



    @field_validator("email")

    @classmethod

    def validate_email(cls, value: str) -> str:

        if len(value) > 120 or not re.fullmatch(

            r"[^@\s]+@[^@\s]+\.[^@\s]+",

            value,

        ):

            raise ValueError("email is invalid or exceeds 120 characters")

        return value



    @field_validator("department")

    @classmethod

    def validate_department(cls, value: str) -> str:

        if not 1 <= len(value) <= 50:

            raise ValueError(

                "department must contain 1 to 50 characters"

            )

        return value



    @field_validator("shift_start", "shift_end")

    @classmethod

    def validate_shift_time(cls, value: str) -> str:

        if not re.fullmatch(

            r"(?:[01]\d|2[0-3]):[0-5]\d",

            value,

        ):

            raise ValueError("shift time must use HH:MM format")

        return value



    @field_validator("joined_on")

    @classmethod

    def validate_joined_on(cls, value: str) -> str:

        parsed = validate_date_model(value, "joined_on")

        return parsed.isoformat()



    @model_validator(mode="after")

    def validate_shift_range(self):

        if self.shift_start == self.shift_end:

            raise ValueError(

                "shift_start and shift_end must differ"

            )

        return self





def validate_date_model(value: str, field_name: str) -> date:

    try:

        parsed = date.fromisoformat(value)

    except (ValueError, TypeError):

        raise ValueError(f"{field_name} must use YYYY-MM-DD format")



    if parsed.isoformat() != value:

        raise ValueError(f"{field_name} must use YYYY-MM-DD format")



    return parsed





class PunchInIn(BaseModel):

    model_config = ConfigDict(strict=True, extra="forbid")



    emp_code: str

    punched_at: Optional[StrictInt] = None

    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"



    @field_validator("punched_at")

    @classmethod

    def validate_punched_at(cls, value):

        if value is not None and not MIN_EPOCH_MS <= value <= MAX_EPOCH_MS:

            raise ValueError(

                "punched_at must be valid epoch milliseconds"

            )

        return value





class PunchOutIn(BaseModel):

    model_config = ConfigDict(strict=True, extra="forbid")



    emp_code: str

    punched_at: Optional[StrictInt] = None



    @field_validator("punched_at")

    @classmethod

    def validate_punched_at(cls, value):

        if value is not None and not MIN_EPOCH_MS <= value <= MAX_EPOCH_MS:

            raise ValueError(

                "punched_at must be valid epoch milliseconds"

            )

        return value





class AttendanceCorrectionIn(BaseModel):

    model_config = ConfigDict(

        strict=True,

        extra="forbid",

        str_strip_whitespace=True,

    )



    status: Optional[Literal[

        "PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"

    ]] = None

    punch_in: Optional[StrictInt] = None

    punch_out: Optional[StrictInt] = None

    reason: str

    regularized_by: str



    @field_validator("punch_in", "punch_out")

    @classmethod

    def validate_timestamps(cls, value):

        if value is not None and not MIN_EPOCH_MS <= value <= MAX_EPOCH_MS:

            raise ValueError(

                "Timestamp must be valid epoch milliseconds"

            )

        return value



    @field_validator("reason")

    @classmethod

    def validate_reason(cls, value):

        if not 5 <= len(value) <= 200:

            raise ValueError(

                "reason must contain 5 to 200 characters"

            )

        return value



    @field_validator("regularized_by")

    @classmethod

    def validate_regularized_by(cls, value):

        if not 1 <= len(value) <= 50:

            raise ValueError(

                "regularized_by must contain 1 to 50 characters"

            )

        return value



# -------------------- Health --------------------



@app.get("/health")

def health():

    try:

        db.command("ping")

        return {"status": "ok"}

    except Exception:

        raise HTTPException(

            status_code=503,

            detail="MongoDB unavailable",

        )





# -------------------- Employees --------------------



@app.post("/employees", status_code=201)

def create_employee(body: EmployeeIn):

    doc = body.model_dump()

    doc["created_at"] = int(

        datetime.now(timezone.utc).timestamp() * 1000

    )



    try:

        db.employees.insert_one(doc)

    except DuplicateKeyError:

        raise HTTPException(

            status_code=409,

            detail="emp_code already exists",

        )



    return serialize_document(doc)





@app.get("/employees")

def list_employees(

    department: Optional[str] = None,

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

):

    query = {}

    if department is not None:

        query["department"] = department



    skip = (page - 1) * page_size

    total = db.employees.count_documents(query)



    items = list(

        db.employees.find(query, {"_id": 0})

        .sort("emp_code", 1)

        .skip(skip)

        .limit(page_size)

    )



    return {

        "items": items,

        "total": total,

        "page": page,

        "page_size": page_size,

    }





# -------------------- Punch-in --------------------



@app.post("/attendance/punch-in", status_code=201)

def punch_in(body: PunchInIn):

    employee = db.employees.find_one(

        {"emp_code": body.emp_code}

    )

    if employee is None:

        raise HTTPException(404, "Employee not found")



    punched_at = epoch_ms_to_ist(body.punched_at)



    attendance_date = attendance_date_for_punch(

        punched_at,

        employee["shift_start"],

        employee["shift_end"],

    )



    # Enforce one record per employee per attendance date.

    # The unique MongoDB index handles concurrent requests.

    metrics = derive_attendance_fields(

        status=body.status,

        punch_in=punched_at,

        punch_out=None,

        employee=employee,

        attendance_date=attendance_date,

    )



    document = {

        "emp_code": body.emp_code,

        "date": attendance_date,

        "status": body.status,

        **metrics,

        "history": [],

    }



    try:

        db.attendance_logs.insert_one(document)

    except DuplicateKeyError:

        raise HTTPException(

            status_code=409,

            detail="already punched in for this date",

        )



    return serialize_value(document)





# -------------------- Punch-out --------------------



@app.post("/attendance/punch-out")

def punch_out(body: PunchOutIn):

    employee = db.employees.find_one(

        {"emp_code": body.emp_code}

    )

    if employee is None:

        raise HTTPException(404, "Employee not found")



    punched_at = epoch_ms_to_ist(body.punched_at)



    # Only an open shift is eligible for punch-out.

    record = db.attendance_logs.find_one(

        {

            "emp_code": body.emp_code,

            "punch_in": {"$ne": None, "$lte": punched_at},

            "$or": [

                {"punch_out": None},

                {"punch_out": {"$exists": False}},

            ],

            "status": {"$in": list(PRESENCE_STATUSES)},

        },

        sort=[("punch_in", -1)],

    )



    if record is None:

        # Distinguish an already-closed shift from a missing punch-in.

        previous = db.attendance_logs.find_one(

            {

                "emp_code": body.emp_code,

                "punch_in": {"$ne": None, "$lte": punched_at},

            },

            sort=[("punch_in", -1)],

        )



        if previous and previous.get("punch_out") is not None:

            raise HTTPException(

                status_code=409,

                detail="already punched out",

            )



        raise HTTPException(

            status_code=404,

            detail="No open punch-in record found",

        )



    punch_in_time = record["punch_in"]



    if punched_at <= punch_in_time:

        raise HTTPException(

            status_code=422,

            detail="punched_at must be after punch_in",

        )



    if punched_at > punch_in_time + timedelta(hours=24):

        raise HTTPException(

            status_code=422,

            detail="punch-out cannot be more than 24 hours after punch-in",

        )



    metrics = derive_attendance_fields(

        status=record["status"],

        punch_in=punch_in_time,

        punch_out=punched_at,

        employee=employee,

        attendance_date=record["date"],

    )



    # Atomic update: exactly one concurrent punch-out can win.

    updated = db.attendance_logs.find_one_and_update(

        {

            "_id": record["_id"],

            "punch_in": punch_in_time,

            "$or": [

                {"punch_out": None},

                {"punch_out": {"$exists": False}},

            ],

        },

        {"$set": metrics},

        return_document=ReturnDocument.AFTER,

    )



    if updated is None:

        raise HTTPException(

            status_code=409,

            detail="Attendance record changed; retry the request",

        )



    return serialize_value(updated)





# -------------------- Attendance listing --------------------



@app.get("/attendance")

def list_attendance(

    emp_code: Optional[str] = None,

    date_from: Optional[str] = None,

    date_to: Optional[str] = None,

    status: Optional[str] = None,

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

):

    query = {}



    if emp_code is not None:

        query["emp_code"] = emp_code



    if date_from is not None:

        validate_iso_date(date_from, "date_from")

        query.setdefault("date", {})["$gte"] = date_from



    if date_to is not None:

        validate_iso_date(date_to, "date_to")

        query.setdefault("date", {})["$lte"] = date_to



    if date_from is not None and date_to is not None:

        if date_from > date_to:

            raise HTTPException(

                status_code=422,

                detail="date_from must be less than or equal to date_to",

            )



    if status is not None:

        if status not in STATUSES:

            raise HTTPException(

                status_code=422,

                detail="Invalid attendance status",

            )

        query["status"] = status



    skip = (page - 1) * page_size

    total = db.attendance_logs.count_documents(query)



    items = list(

        db.attendance_logs.find(query, {"_id": 0})

        .sort([("date", -1), ("emp_code", 1)])

        .skip(skip)

        .limit(page_size)

    )



    return {

        "items": [serialize_value(item) for item in items],

        "total": total,

        "page": page,

        "page_size": page_size,

    }





# -------------------- Attendance correction / regularization --------------------




@app.patch("/attendance/{emp_code}/{date}")
def correct_attendance(
    emp_code: str,
    date: str,
    body: AttendanceCorrectionIn,
):
    validate_iso_date(date, "date")




    employee = db.employees.find_one({"emp_code": emp_code})

    if employee is None:

        raise HTTPException(404, "Employee not found")



    record = db.attendance_logs.find_one({

        "emp_code": emp_code,

        "date": date,

    })

    if record is None:

        raise HTTPException(404, "Attendance record not found")



    changes = body.model_dump(

        exclude_unset=True,

        exclude={"reason", "regularized_by"},

    )



    if not changes:

        raise HTTPException(

            status_code=422,

            detail="Provide at least one field to correct",

        )



    old_status = record.get("status")

    new_status = changes.get("status", old_status)



    old_in = record.get("punch_in")

    old_out = record.get("punch_out")



    new_in = (

        epoch_ms_to_ist(changes["punch_in"])

        if "punch_in" in changes and changes["punch_in"] is not None

        else (None if "punch_in" in changes else old_in)

    )

    new_out = (

        epoch_ms_to_ist(changes["punch_out"])

        if "punch_out" in changes and changes["punch_out"] is not None

        else (None if "punch_out" in changes else old_out)

    )



    if new_status in {"ABSENT", "LEAVE"}:

        if (

            "punch_in" in changes and changes["punch_in"] is not None

        ) or (

            "punch_out" in changes and changes["punch_out"] is not None

        ):

            raise HTTPException(

                status_code=422,

                detail="ABSENT and LEAVE cannot have punch times",

            )

        new_in = None

        new_out = None

    else:

        if new_in is None:

            raise HTTPException(

                status_code=422,

                detail="Presence statuses require punch_in",

            )



        if new_in.date().isoformat() != date:

            raise HTTPException(

                status_code=422,

                detail="punch_in must fall on the attendance date",

            )



    # Compare only source fields. Derived metrics are server-owned.

    old_values = {

        "status": old_status,

        "punch_in": old_in,

        "punch_out": old_out,

    }

    new_values = {

        "status": new_status,

        "punch_in": new_in,

        "punch_out": new_out,

    }



    actual_changes = {

        field: {

            "from": old_values[field],

            "to": new_values[field],

        }

        for field in ("status", "punch_in", "punch_out")

        if old_values[field] != new_values[field]

    }



    if not actual_changes:

        raise HTTPException(

            status_code=422,

            detail="Correction does not change any values",

        )



    metrics = derive_attendance_fields(

        status=new_status,

        punch_in=new_in,

        punch_out=new_out,

        employee=employee,

        attendance_date=date,

    )



    update_fields = {

        "status": new_status,

        **metrics,

    }



    history_entry = {

        "at": int(datetime.now(timezone.utc).timestamp() * 1000),

        "by": body.regularized_by,

        "reason": body.reason,

        "changes": {

            key: {

                "from": serialize_value(value["from"]),

                "to": serialize_value(value["to"]),

            }

            for key, value in actual_changes.items()

        },

    }



    # Compare-and-set: don't overwrite a correction based on stale data.

    concurrency_filter = {

        "_id": record["_id"],

        "status": old_status,

        "punch_in": old_in,

        "punch_out": old_out,

    }



    updated = db.attendance_logs.find_one_and_update(

        concurrency_filter,

        {

            "$set": update_fields,

            "$push": {"history": history_entry},

        },

        return_document=ReturnDocument.AFTER,

    )



    if updated is None:

        raise HTTPException(

            status_code=409,

            detail="Attendance record changed concurrently; retry",

        )



    return serialize_value(updated)



# ============================================================

# PART 3: ANALYTICS ENDPOINTS

# ============================================================



PRESENCE_STATUSES = ["PRESENT", "WFH", "ON_DUTY"]





def month_bounds(month: str) -> tuple[str, str]:

    """Return the inclusive ISO date bounds for a YYYY-MM month."""

    validate_month(month)

    year, month_number = map(int, month.split("-"))

    last_day = calendar.monthrange(year, month_number)[1]

    return f"{month}-01", f"{month}-{last_day:02d}"





def weekday_count(start_date: str, end_date: str) -> int:

    """Count weekdays in an inclusive ISO date range."""

    start = date.fromisoformat(start_date)

    end = date.fromisoformat(end_date)

    total = 0

    current = start



    while current <= end:

        if current.weekday() < 5:

            total += 1

        current += timedelta(days=1)



    return total





def round_half_up_number(value, places: int = 2):

    """Round a numeric value using the project's half-up rounding helper."""

    if value is None:

        return None

    return round_decimal(value, places)





@app.get("/analytics/employees/{emp_code}/monthly")

def employee_monthly_analytics(

    emp_code: str,

    month: str = Query(..., description="Month in YYYY-MM format"),

):

    start_date, end_date = month_bounds(month)



    employee = employees_collection.find_one(

        {"emp_code": emp_code},

        {"_id": 0, "emp_code": 1, "name": 1, "department": 1, "joined_on": 1},

    )

    if employee is None:

        raise HTTPException(status_code=404, detail="Employee not found")



    # A new employee is only counted from their joining date.

    effective_start = max(start_date, employee["joined_on"])

    working_days = (

        weekday_count(effective_start, end_date)

        if effective_start <= end_date

        else 0

    )



    pipeline = [

        {

            "$match": {

                "emp_code": emp_code,

                "date": {"$gte": start_date, "$lte": end_date},

            }

        },

        {

            "$addFields": {

                "_date_obj": {

                    "$dateFromString": {

                        "dateString": "$date",

                        "format": "%Y-%m-%d",

                        "onError": None,

                        "onNull": None,

                    }

                }

            }

        },

        {

            "$addFields": {

                "_weekday": {

                    "$dayOfWeek": "$_date_obj"

                }

            }

        },

        {

            "$group": {

                "_id": None,

                "present_days": {

                    "$sum": {

                        "$cond": [

                            {

                                "$and": [

                                    {"$in": ["$status", PRESENCE_STATUSES]},

                                    {"$gte": ["$_weekday", 2]},

                                    {"$lte": ["$_weekday", 6]},

                                ]

                            },

                            {

                                "$cond": [

                                    {"$eq": [{"$ifNull": ["$half_day", False]}, True]},

                                    0.5,

                                    1.0,

                                ]

                            },

                            0,

                        ]

                    }

                },

                "leave_days": {

                    "$sum": {

                        "$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]

                    }

                },

                "late_count": {

                    "$sum": {

                        "$cond": [

                            {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},

                            1,

                            0,

                        ]

                    }

                },

            }

        },

    ]



    result = list(attendance_collection.aggregate(pipeline))

    metrics = result[0] if result else {

        "present_days": 0,

        "leave_days": 0,

        "late_count": 0,

    }



    present_days = round_half_up_number(metrics["present_days"], 2)

    attendance_pct = (

        round_half_up_number((present_days / working_days) * 100, 4)

        if working_days > 0

        else None

    )



    total_late_pipeline = [

        {"$match": {"emp_code": emp_code, "date": {"$gte": start_date, "$lte": end_date}}},

        {"$group": {"_id": None, "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}}, "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}}}},

    ]

    totals = list(attendance_collection.aggregate(total_late_pipeline))

    total_late_minutes = totals[0]["total_late_minutes"] if totals else 0

    total_overtime_minutes = totals[0]["total_overtime_minutes"] if totals else 0



    return {

        "emp_code": employee["emp_code"],

        "month": month,

        "working_days": working_days,

        "present_days": present_days,

        "leave_days": metrics["leave_days"],

        "late_count": metrics["late_count"],

        "total_late_minutes": int(total_late_minutes),

        "total_overtime_minutes": int(total_overtime_minutes),

        "attendance_pct": attendance_pct,

    }





@app.get("/analytics/departments/summary")

def department_summary(

    month: str = Query(..., description="Month in YYYY-MM format"),

    department: str | None = Query(None),

):

    start_date, end_date = month_bounds(month)



    employee_match = {"joined_on": {"$lte": end_date}}

    if department is not None:

        employee_match["department"] = department



    pipeline = [

        {"$match": employee_match},

        {

            "$lookup": {

                "from": "attendance_logs",

                "let": {"employee_code": "$emp_code"},

                "pipeline": [

                    {

                        "$match": {

                            "$expr": {

                                "$and": [

                                    {"$eq": ["$emp_code", "$$employee_code"]},

                                    {"$gte": ["$date", start_date]},

                                    {"$lte": ["$date", end_date]},

                                ]

                            }

                        }

                    },

                    {

                        "$addFields": {

                            "_date_obj": {

                                "$dateFromString": {

                                    "dateString": "$date",

                                    "format": "%Y-%m-%d",

                                    "onError": None,

                                    "onNull": None,

                                }

                            }

                        }

                    },

                    {

                        "$addFields": {

                            "_weekday": {"$dayOfWeek": "$_date_obj"}

                        }

                    },

                ],

                "as": "logs",

            }

        },

        {

            "$unwind": {

                "path": "$logs",

                "preserveNullAndEmptyArrays": True,

            }

        },

        {

            "$group": {

                "_id": "$department",

                "_employees": {"$addToSet": "$emp_code"},

                "present_days": {

                    "$sum": {

                        "$cond": [

                            {

                                "$and": [

                                    {"$in": ["$logs.status", PRESENCE_STATUSES]},

                                    {"$gte": ["$logs._weekday", 2]},

                                    {"$lte": ["$logs._weekday", 6]},

                                ]

                            },

                            {

                                "$cond": [

                                    {

                                        "$eq": [

                                            {"$ifNull": ["$logs.half_day", False]},

                                            True,

                                        ]

                                    },

                                    0.5,

                                    1.0,

                                ]

                            },

                            0,

                        ]

                    }

                },

                "avg_work_hours": {

                    "$avg": {

                        "$cond": [

                            {

                                "$and": [

                                    {"$in": ["$logs.status", PRESENCE_STATUSES]},

                                    {"$ne": ["$logs.work_hours", None]},

                                ]

                            },

                            "$logs.work_hours",

                            None,

                        ]

                    }

                },

                "late_count": {

                    "$sum": {

                        "$cond": [

                            {"$gt": [{"$ifNull": ["$logs.late_minutes", 0]}, 0]},

                            1,

                            0,

                        ]

                    }

                },

                "total_late_minutes": {

                    "$sum": {"$ifNull": ["$logs.late_minutes", 0]}

                },

                "leave_count": {

                    "$sum": {

                        "$cond": [

                            {"$eq": ["$logs.status", "LEAVE"]},

                            1,

                            0,

                        ]

                    }

                },

                "on_duty_count": {

                    "$sum": {

                        "$cond": [

                            {"$eq": ["$logs.status", "ON_DUTY"]},

                            1,

                            0,

                        ]

                    }

                },

            }

        },

        {

            "$project": {

                "_id": 0,

                "department": "$_id",

                "headcount": {"$size": "$_employees"},

                "present_days": {"$round": ["$present_days", 2]},

                "avg_work_hours": {"$round": ["$avg_work_hours", 2]},

                "late_count": 1,

                "total_late_minutes": 1,

                "leave_count": 1,

                "on_duty_count": 1,

            }

        },

        {"$sort": {"department": 1}},

    ]



    rows = list(employees_collection.aggregate(pipeline))



    # The lookup starts from employees, so departments with employees but no

    # attendance records are retained with zero attendance metrics.

    return {

        "month": month,

        "items": rows,

    }





@app.get("/analytics/leaderboard/late")

def late_arrival_leaderboard(

    month: str = Query(..., description="Month in YYYY-MM format"),

    limit: int = Query(10, ge=1, le=50),

    department: str | None = Query(None),

):

    start_date, end_date = month_bounds(month)



    pipeline = [

        {

            "$match": {

                "date": {"$gte": start_date, "$lte": end_date},

                "late_minutes": {"$gt": 0},

            }

        },

        {

            "$lookup": {

                "from": "employees",

                "localField": "emp_code",

                "foreignField": "emp_code",

                "as": "employee",

            }

        },

        {"$unwind": "$employee"},

    ]



    # Filter department before grouping and ranking.

    if department is not None:

        pipeline.append({"$match": {"employee.department": department}})



    pipeline.extend(

        [

            {

                "$group": {

                    "_id": "$emp_code",

                    "name": {"$first": "$employee.name"},

                    "department": {"$first": "$employee.department"},

                    "total_late_minutes": {"$sum": "$late_minutes"},

                    "late_count": {"$sum": 1},

                }

            },

            {

                "$setWindowFields": {

                    "sortBy": {"total_late_minutes": -1},

                    "output": {"rank": {"$rank": {}}},

                }

            },

            {"$match": {"rank": {"$lte": limit}}},

            {"$sort": {"rank": 1, "_id": 1}},

            {

                "$project": {

                    "_id": 0,

                    "emp_code": "$_id",

                    "name": 1,

                    "department": 1,

                    "total_late_minutes": 1,

                    "late_count": 1,

                    "rank": 1,

                }

            },

        ]

    )



    rows = list(attendance_collection.aggregate(pipeline))



    return {

        "month": month,

        "items": rows,

    }



# ============================================================

# PART 4: DEPARTMENT TREND + QUERY EXPLAIN

# ============================================================



from datetime import datetime, time, timezone





@app.get("/analytics/departments/{department}/trend")

def department_attendance_trend(

    department: str,

    from_date: str = Query(..., alias="from"),

    to_date: str = Query(..., alias="to"),

):

    # Validate ISO date strings and the requested range.

    start_date = validate_iso_date(from_date)

    end_date = validate_iso_date(to_date)



    if end_date < start_date:

        raise HTTPException(

            status_code=422,

            detail="'to' must be greater than or equal to 'from'",

        )



    if (end_date - start_date).days + 1 > 92:

        raise HTTPException(

            status_code=422,

            detail="Date range cannot exceed 92 days",

        )

    # Attendance and joined_on dates are stored as ISO YYYY-MM-DD strings.
    # Keep date objects for validation/densify bounds, but use strings in MongoDB filters.
    start_text = start_date.isoformat()
    end_text = end_date.isoformat()
    if not employees_collection.find_one({"department": department}):

        raise HTTPException(status_code=404, detail="Department not found")



    # MongoDB generates missing dates; no Python date-filling loop is used.

    pipeline = [

        {

            "$match": {

                "department": department,

                "joined_on": {"$lte": end_text},

            }

        },

        {

            "$lookup": {

                "from": "attendance_logs",

                "let": {"employee_code": "$emp_code"},

                "pipeline": [

                    {

                        "$match": {

                            "$expr": {

                                "$and": [

                                    {"$eq": ["$emp_code", "$$employee_code"]},

                                    {"$gte": ["$date", start_text]},

                                    {"$lte": ["$date", end_text]},

                                ]

                            }

                        }

                    },

                    {

                        "$addFields": {

                            "_day": {

                                "$dateFromString": {

                                    "dateString": "$date",

                                    "format": "%Y-%m-%d",

                                    "onError": None,

                                    "onNull": None,

                                }

                            }

                        }

                    },

                ],

                "as": "logs",

            }

        },

        {

            "$unwind": {

                "path": "$logs",

                "preserveNullAndEmptyArrays": True,

            }

        },

{
    "$unionWith": {
        "coll": "employees",
        "pipeline": [
            {"$match": {"department": department}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "logs": {
                        "date": {"$literal": start_text},
                        "status": {"$literal": None},
                        "half_day": {"$literal": False},
                        "late_minutes": {"$literal": 0},
                    },
                }
            },
        ],
    }
},


        {

            "$group": {

                "_id": "$logs.date",

                "present_count": {

                    "$sum": {

                        "$cond": [

                            {

                                "$in": [

                                    "$logs.status",

                                    PRESENCE_STATUSES,

                                ]

                            },

                            {

                                "$cond": [

                                    {

                                        "$eq": [

                                            {"$ifNull": ["$logs.half_day", False]},

                                            True,

                                        ]

                                    },

                                    0.5,

                                    1.0,

                                ]

                            },

                            0,

                        ]

                    }

                },

                "late_count": {

                    "$sum": {

                        "$cond": [

                            {

                                "$gt": [

                                    {"$ifNull": ["$logs.late_minutes", 0]},

                                    0,

                                ]

                            },

                            1,

                            0,

                        ]

                    }

                },

            }

        },

        {

            "$project": {

                "_id": 0,

                "date": "$_id",

                "present_count": 1,

                "late_count": 1,

            }

        },

        {

            "$match": {

                "date": {"$ne": None}

            }

        },

        {

            "$addFields": {

                "_date": {

                    "$dateFromString": {

                        "dateString": "$date",

                        "format": "%Y-%m-%d",

                    }

                }

            }

        },

        {

            "$densify": {

                "field": "_date",

                "range": {

                    "step": 1,

                    "unit": "day",

                    "bounds": [

                        datetime.combine(start_date, time.min),

                        datetime.combine(end_date + timedelta(days=1), time.min),

                    ],

                },

            }

        },

        {

            "$addFields": {

                "date": {

                    "$dateToString": {

                        "format": "%Y-%m-%d",

                        "date": "$_date",

                    }

                },

                "present_count": {"$ifNull": ["$present_count", 0]},

                "late_count": {"$ifNull": ["$late_count", 0]},

                "weekday_number": {"$dayOfWeek": "$_date"},

            }

        },

        {

            "$lookup": {

                "from": "employees",

                "let": {"trend_date": "$date"},

                "pipeline": [

                    {

                        "$match": {

                            "$expr": {

                                "$and": [

                                    {"$eq": ["$department", department]},

                                    {"$lte": ["$joined_on", "$$trend_date"]},

                                ]

                            }

                        }

                    },

                    {"$count": "count"},

                ],

                "as": "headcount_result",

            }

        },

        {

            "$addFields": {

                "headcount": {

                    "$ifNull": [

                        {"$arrayElemAt": ["$headcount_result.count", 0]},

                        0,

                    ]

                },

                "is_working_day": {

                    "$and": [

                        {"$gte": ["$weekday_number", 2]},

                        {"$lte": ["$weekday_number", 6]},

                    ]

                },

            }

        },

        {

            "$addFields": {

                "attendance_rate": {

                    "$cond": [

                        {

                            "$and": [

                                "$is_working_day",

                                {"$gt": ["$headcount", 0]},

                            ]

                        },

                        {

                            "$round": [

                                {

                                    "$divide": [

                                        "$present_count",

                                        "$headcount",

                                    ]

                                },

                                4,

                            ]

                        },

                        None,

                    ]

                }

            }

        },

        {

            "$setWindowFields": {

                "sortBy": {"_date": 1},

                "output": {

                    "moving_avg_7d": {

                        "$avg": "$attendance_rate",

                        "window": {"documents": [-6, 0]},

                    }

                },

            }

        },

        {

            "$project": {

                "_id": 0,

                "date": 1,

                "is_working_day": 1,

                "headcount": 1,

                "present_count": 1,

                "late_count": 1,

                "attendance_rate": 1,

                "moving_avg_7d": {"$round": ["$moving_avg_7d", 4]},

            }

        },

        {"$sort": {"date": 1}},

    ]



    results = list(employees_collection.aggregate(pipeline))



    if not results:

        results = [

            {

                "date": (start_date + timedelta(days=offset)).isoformat(),

                "is_working_day": (start_date + timedelta(days=offset)).weekday() < 5,

                "headcount": 0,

                "present_count": 0,

                "late_count": 0,

                "attendance_rate": None,

                "moving_avg_7d": None,

            }

            for offset in range((end_date - start_date).days + 1)

        ]



    for row in results:

        headcount = row.get("headcount") or 0

        if row.get("is_working_day") and headcount > 0:

            row["attendance_rate"] = round_half_up_number(

                row["present_count"] / headcount,

                4,

            )

        else:

            row["attendance_rate"] = None



        if row.get("moving_avg_7d") is not None:

            row["moving_avg_7d"] = round_half_up_number(

                row["moving_avg_7d"],

                4,

            )



    return {

        "department": department,

        "items": results,

    }






@app.get("/admin/explain/{endpoint}")
def explain_query(
    endpoint: Literal[
        "attendance_list",
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
        "department_trend",
    ],
    month: str | None = Query(None),
    emp_code: str | None = Query(None),
    department: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    """Explain the database query used by each supported API operation."""
    explanation = None
    collection = attendance_collection.name
    start_date = end_date = None

    if endpoint in {
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
    }:
        if month is None:
            raise HTTPException(
                status_code=422,
                detail="month is required for this explain endpoint",
            )
        start_date, end_date = month_bounds(month)

    if endpoint == "attendance_list":
        match = {}

        if emp_code is not None:
            match["emp_code"] = emp_code

        if date_from is not None:
            validate_iso_date(date_from, "date_from")
            match.setdefault("date", {})["$gte"] = date_from

        if date_to is not None:
            validate_iso_date(date_to, "date_to")
            match.setdefault("date", {})["$lte"] = date_to

        if (
            date_from is not None
            and date_to is not None
            and date_to < date_from
        ):
            raise HTTPException(
                status_code=422,
                detail="date_from must be less than or equal to date_to",
            )

        if status is not None:
            if status not in STATUSES:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid attendance status",
                )
            match["status"] = status

        command = {
            "find": attendance_collection.name,
            "filter": match,
            "sort": {"date": -1, "emp_code": 1},
            "skip": (page - 1) * page_size,
            "limit": page_size,
        }

        explanation = attendance_collection.database.command(
            "explain",
            command,
            verbosity="executionStats",
        )

    elif endpoint == "employee_monthly":
        if not emp_code:
            raise HTTPException(
                status_code=422,
                detail="emp_code is required for employee_monthly",
            )

        employee = employees_collection.find_one(
            {"emp_code": emp_code},
            {"_id": 0, "joined_on": 1},
        )

        if employee is None:
            raise HTTPException(
                status_code=404,
                detail="Employee not found",
            )

        effective_start = max(start_date, employee["joined_on"])

        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {
                        "$gte": start_date,
                        "$lte": end_date,
                    },
                }
            },
            {
                "$addFields": {
                    "_date_obj": {
                        "$dateFromString": {
                            "dateString": "$date",
                            "format": "%Y-%m-%d",
                            "onError": None,
                            "onNull": None,
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "_weekday": {"$dayOfWeek": "$_date_obj"}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {
                                            "$in": [
                                                "$status",
                                                list(PRESENCE_STATUSES),
                                            ]
                                        },
                                        {"$gte": ["$_weekday", 2]},
                                        {"$lte": ["$_weekday", 6]},
                                    ]
                                },
                                {
                                    "$cond": [
                                        {
                                            "$eq": [
                                                {
                                                    "$ifNull": [
                                                        "$half_day",
                                                        False,
                                                    ]
                                                },
                                                True,
                                            ]
                                        },
                                        0.5,
                                        1.0,
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                    "leave_days": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", "LEAVE"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        {"$ifNull": ["$late_minutes", 0]},
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$late_minutes", 0]}
                    },
                    "total_overtime_minutes": {
                        "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                    },
                }
            },
        ]

        explanation = attendance_collection.database.command(
            "explain",
            {
                "aggregate": attendance_collection.name,
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        employee_explain = employees_collection.database.command(
            "explain",
            {
                "find": employees_collection.name,
                "filter": {"emp_code": emp_code},
                "limit": 1,
            },
            verbosity="executionStats",
        )

        explanation = {
            "attendance_query": explanation,
            "employee_lookup": employee_explain,
            "effective_start": effective_start,
        }

    elif endpoint == "department_summary":
        collection = employees_collection.name

        employee_match = {"joined_on": {"$lte": end_date}}

        if department is not None:
            employee_match["department"] = department

        pipeline = [
            {"$match": employee_match},
            {
                "$lookup": {
                    "from": attendance_collection.name,
                    "let": {"employee_code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {
                                            "$eq": [
                                                "$emp_code",
                                                "$$employee_code",
                                            ]
                                        },
                                        {"$gte": ["$date", start_date]},
                                        {"$lte": ["$date", end_date]},
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "logs",
                }
            },
            {
                "$unwind": {
                    "path": "$logs",
                    "preserveNullAndEmptyArrays": True,
                }
            },
            {
                "$group": {
                    "_id": "$department",
                    "employees": {"$addToSet": "$emp_code"},
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {
                                            "$in": [
                                                "$logs.status",
                                                list(PRESENCE_STATUSES),
                                            ]
                                        },
                                        {
                                            "$gte": [
                                                {
                                                    "$dayOfWeek": {
                                                        "$dateFromString": {
                                                            "dateString": "$logs.date",
                                                            "onError": None,
                                                            "onNull": None,
                                                        }
                                                    }
                                                },
                                                2,
                                            ]
                                        },
                                        {
                                            "$lte": [
                                                {
                                                    "$dayOfWeek": {
                                                        "$dateFromString": {
                                                            "dateString": "$logs.date",
                                                            "onError": None,
                                                            "onNull": None,
                                                        }
                                                    }
                                                },
                                                6,
                                            ]
                                        },
                                    ]
                                },
                                {
                                    "$cond": [
                                        {
                                            "$eq": [
                                                {
                                                    "$ifNull": [
                                                        "$logs.half_day",
                                                        False,
                                                    ]
                                                },
                                                True,
                                            ]
                                        },
                                        0.5,
                                        1.0,
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                    "avg_work_hours": {
                        "$avg": {
                            "$cond": [
                                {
                                    "$and": [
                                        {
                                            "$in": [
                                                "$logs.status",
                                                list(PRESENCE_STATUSES),
                                            ]
                                        },
                                        {"$ne": ["$logs.work_hours", None]},
                                    ]
                                },
                                "$logs.work_hours",
                                None,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        {
                                            "$ifNull": [
                                                "$logs.late_minutes",
                                                0,
                                            ]
                                        },
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {
                            "$ifNull": ["$logs.late_minutes", 0]
                        }
                    },
                    "leave_count": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$logs.status", "LEAVE"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "on_duty_count": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$logs.status", "ON_DUTY"]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        explanation = employees_collection.database.command(
            "explain",
            {
                "aggregate": employees_collection.name,
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    elif endpoint == "late_leaderboard":
        pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": start_date,
                        "$lte": end_date,
                    },
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$lookup": {
                    "from": employees_collection.name,
                    "localField": "emp_code",
                    "foreignField": "emp_code",
                    "as": "employee",
                }
            },
            {"$unwind": "$employee"},
        ]

        if department is not None:
            pipeline.append(
                {"$match": {"employee.department": department}}
            )

        pipeline.extend(
            [
                {
                    "$group": {
                        "_id": "$emp_code",
                        "name": {"$first": "$employee.name"},
                        "department": {
                            "$first": "$employee.department"
                        },
                        "total_late_minutes": {"$sum": "$late_minutes"},
                        "late_count": {"$sum": 1},
                    }
                },
                {
                    "$setWindowFields": {
                        "sortBy": {"total_late_minutes": -1},
                        "output": {"rank": {"$rank": {}}},
                    }
                },
                {"$match": {"rank": {"$lte": limit}}},
                {"$sort": {"rank": 1, "_id": 1}},
            ]
        )

        explanation = attendance_collection.database.command(
            "explain",
            {
                "aggregate": attendance_collection.name,
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    else:  # department_trend
        collection = employees_collection.name

        if from_date is None or to_date is None or department is None:
            raise HTTPException(
                status_code=422,
                detail="'from', 'to', and 'department' are required",
            )

        start = validate_iso_date(from_date, "from")
        end = validate_iso_date(to_date, "to")

        if end < start:
            raise HTTPException(
                status_code=422,
                detail="'to' must be greater than or equal to 'from'",
            )

        if (end - start).days + 1 > 92:
            raise HTTPException(
                status_code=422,
                detail="Date range cannot exceed 92 days",
            )

        if not employees_collection.find_one(
            {"department": department},
            {"_id": 1},
        ):
            raise HTTPException(
                status_code=404,
                detail="Department not found",
            )

        start_text = start.isoformat()
        end_text = end.isoformat()


        pipeline = [
            {
                "$match": {
                    "department": department,
                    "joined_on": {"$lte": end_text},
                }
            },
            {
                "$lookup": {
                    "from": attendance_collection.name,
                    "let": {"employee_code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {
                                            "$eq": [
                                                "$emp_code",
                                                "$$employee_code",
                                            ]
                                        },
                                        {"$gte": ["$date", start_text]},
                                        {"$lte": ["$date", end_text]},
                                    ]
                                }
                            }
                        },
                        {
                            "$addFields": {
                                "_day": {
                                    "$dateFromString": {
                                        "dateString": "$date",
                                        "format": "%Y-%m-%d",
                                        "onError": None,
                                        "onNull": None,
                                    }
                                }
                            }
                        },
                    ],
                    "as": "logs",
                }
            },
            {
                "$unwind": {
                    "path": "$logs",
                    "preserveNullAndEmptyArrays": True,
                }
            },
            {
                "$group": {
                    "_id": "$logs.date",
                    "present_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$in": [
                                        "$logs.status",
                                        list(PRESENCE_STATUSES),
                                    ]
                                },
                                {
                                    "$cond": [
                                        {
                                            "$eq": [
                                                {
                                                    "$ifNull": [
                                                        "$logs.half_day",
                                                        False,
                                                    ]
                                                },
                                                True,
                                            ]
                                        },
                                        0.5,
                                        1.0,
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        {
                                            "$ifNull": [
                                                "$logs.late_minutes",
                                                0,
                                            ]
                                        },
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$match": {"_id": {"$ne": None}}},
            {
                "$project": {
                    "_id": 0,
                    "date": "$_id",
                    "present_count": 1,
                    "late_count": 1,
                }
            },
            {"$match": {"date": {"$ne": None}}},
            {
                "$addFields": {
                    "_date": {
                        "$dateFromString": {
                            "dateString": "$date",
                            "format": "%Y-%m-%d",
                        }
                    }
                }
            },
            {
                "$densify": {
                    "field": "_date",
                    "range": {
                        "step": 1,
                        "unit": "day",
                        "bounds": [
                            datetime.combine(start, time.min),
                            datetime.combine(
                                end + timedelta(days=1),
                                time.min,
                            ),
                        ],
                    },
                }
            },
            {
                "$addFields": {
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$_date",
                        }
                    },
                    "present_count": {
                        "$ifNull": ["$present_count", 0]
                    },
                    "late_count": {
                        "$ifNull": ["$late_count", 0]
                    },
                    "weekday_number": {"$dayOfWeek": "$_date"},
                }
            },
            {
                "$lookup": {
                    "from": employees_collection.name,
                    "let": {"trend_date": "$date"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$department", department]},
                                        {
                                            "$lte": [
                                                "$joined_on",
                                                "$$trend_date",
                                            ]
                                        },
                                    ]
                                }
                            }
                        },
                        {"$count": "count"},
                    ],
                    "as": "headcount_result",
                }
            },
            {
                "$addFields": {
                    "headcount": {
                        "$ifNull": [
                            {
                                "$arrayElemAt": [
                                    "$headcount_result.count",
                                    0,
                                ]
                            },
                            0,
                        ]
                    },
                    "is_working_day": {
                        "$and": [
                            {"$gte": ["$weekday_number", 2]},
                            {"$lte": ["$weekday_number", 6]},
                        ]
                    },
                }
            },
            {
                "$addFields": {
                    "attendance_rate": {
                        "$cond": [
                            {
                                "$and": [
                                    "$is_working_day",
                                    {"$gt": ["$headcount", 0]},
                                ]
                            },
                            {
                                "$round": [
                                    {
                                        "$divide": [
                                            "$present_count",
                                            "$headcount",
                                        ]
                                    },
                                    4,
                                ]
                            },
                            None,
                        ]
                    }
                }
            },
            {
                "$setWindowFields": {
                    "sortBy": {"_date": 1},
                    "output": {
                        "moving_avg_7d": {
                            "$avg": "$attendance_rate",
                            "window": {"documents": [-6, 0]},
                        }
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "date": 1,
                    "is_working_day": 1,
                    "headcount": 1,
                    "present_count": 1,
                    "late_count": 1,
                    "attendance_rate": 1,
                    "moving_avg_7d": {
                        "$round": ["$moving_avg_7d", 4]
                    },
                }
            },
            {"$sort": {"date": 1}},
        ]


        explanation = employees_collection.database.command(
            "explain",
            {
                "aggregate": employees_collection.name,
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    return {
        "endpoint": endpoint,
        "collection": collection,
        "query": {
            "month": month,
            "emp_code": emp_code,
            "department": department,
            "date_from": date_from,
            "date_to": date_to,
            "status": status,
            "limit": limit,
            "page": page,
            "page_size": page_size,
            "from": from_date,
            "to": to_date,
        },
        "explain": explanation,
    }
