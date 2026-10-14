
def test_create_employee_success(api_client):
    payload = {
        "emp_code": "EMP9001",
        "name": "Test Employee",
        "email": "test9001@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    response = api_client.post("/employees", json=payload)

    assert response.status_code in (200, 201)
    assert response.json()["emp_code"] == "EMP9001"


def test_duplicate_employee_code_returns_conflict(api_client):
    payload = {
        "emp_code": "EMP9002",
        "name": "Duplicate Test",
        "email": "duplicate9002@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    first = api_client.post("/employees", json=payload)
    second = api_client.post("/employees", json=payload)

    assert first.status_code in (200, 201)
    assert second.status_code == 409


def test_invalid_employee_code_is_rejected(api_client):
    payload = {
        "emp_code": "INVALID",
        "name": "Invalid Employee",
        "email": "invalid@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    response = api_client.post("/employees", json=payload)

    assert response.status_code == 422

def test_attendance_punch_out_success(api_client):
    employee = {
        "emp_code": "EMP9201",
        "name": "Punch Out Test",
        "email": "attendance9201@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9201",
            "punched_at": 1791871200000,
        },
    )
    assert punch_in.status_code in (200, 201)

    punch_out = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9201",
            "punched_at": 1791903600000,
        },
    )

    assert punch_out.status_code in (200, 201)

    result = punch_out.json()
    assert result["punch_out"] is not None
    assert result["work_hours"] is not None


def test_punch_out_without_punch_in_returns_404(api_client):
    employee = {
        "emp_code": "EMP9202",
        "name": "Missing Punch In",
        "email": "attendance9202@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    response = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9202",
            "punched_at": 1791903600000,
        },
    )

    assert response.status_code == 404
def test_attendance_punch_in_success(api_client):
    employee = {
        "emp_code": "EMP9101",
        "name": "Attendance Test",
        "email": "attendance9101@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    employee_response = api_client.post("/employees", json=employee)
    assert employee_response.status_code in (200, 201)

    response = api_client.post(
        "/attendance/punch-in",
        json={"emp_code": "EMP9101"},
    )

    assert response.status_code in (200, 201)


def test_punch_in_unknown_employee_returns_404(api_client):
    response = api_client.post(
        "/attendance/punch-in",
        json={"emp_code": "EMP9199"},
    )

    assert response.status_code == 404


def test_duplicate_punch_in_returns_conflict(api_client):
    employee = {
        "emp_code": "EMP9102",
        "name": "Duplicate Punch Test",
        "email": "attendance9102@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    employee_response = api_client.post("/employees", json=employee)
    assert employee_response.status_code in (200, 201)

    first = api_client.post(
        "/attendance/punch-in",
        json={"emp_code": "EMP9102"},
    )

    second = api_client.post(
        "/attendance/punch-in",
        json={"emp_code": "EMP9102"},
    )

    assert first.status_code in (200, 201)
    assert second.status_code == 409



def test_second_punch_out_returns_conflict(api_client):
    employee = {
        "emp_code": "EMP9203",
        "name": "Second Punch Out",
        "email": "attendance9203@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9203",
            "punched_at": 1791871200000,
        },
    )

    first = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9203",
            "punched_at": 1791903600000,
        },
    )

    second = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9203",
            "punched_at": 1791907200000,
        },
    )

    assert first.status_code in (200, 201)
    assert second.status_code == 409

def test_attendance_list_returns_valid_response(api_client):
    response = api_client.get("/attendance")

    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_attendance_filter_by_employee_code(api_client):
    employee = {
        "emp_code": "EMP9301",
        "name": "Attendance Filter Test",
        "email": "attendance9301@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9301",
            "punched_at": 1791871200000,
        },
    )
    assert punch_in.status_code in (200, 201)

    response = api_client.get(
        "/attendance",
        params={"emp_code": "EMP9301"},
    )

    assert response.status_code == 200

    body = response.json()
    records = body.get("items", body.get("data", []))

    assert isinstance(records, list)
    assert any(record.get("emp_code") == "EMP9301" for record in records)



def test_attendance_regularization_requires_reason(api_client):
    employee = {
        "emp_code": "EMP9401",
        "name": "Regularization Test",
        "email": "attendance9401@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9401",
            "punched_at": 1791871200000,
        },
    )
    assert punch_in.status_code in (200, 201)

    response = api_client.patch(
        "/attendance/EMP9401/2026-10-12",
        json={
            "status": "WFH",
            "regularized_by": "admin",
        },
    )

    assert response.status_code == 422

def test_successful_regularization_records_history(api_client):
    employee = {
        "emp_code": "EMP9402",
        "name": "Regularization Audit Test",
        "email": "attendance9402@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9402",
            "punched_at": 1791871200000,
        },
    )
    assert punch_in.status_code in (200, 201)

    # Derive the attendance date from the returned record.
    record = punch_in.json()
    attendance_date = record.get("date", "2026-10-12")

    response = api_client.patch(
        f"/attendance/EMP9402/{attendance_date}",
        json={
            "status": "WFH",
            "reason": "Approved remote work",
            "regularized_by": "admin",
        },
    )

    assert response.status_code in (200, 201)

    updated = response.json()
    assert updated["status"] == "WFH"
    assert len(updated["history"]) == 1

def test_employee_monthly_analytics_success(api_client):
    employee = {
        "emp_code": "EMP9501",
        "name": "Monthly Analytics Test",
        "email": "analytics9501@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    response = api_client.get(
        "/analytics/employees/EMP9501/monthly",
        params={"month": "2026-10"},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
def test_employee_monthly_analytics_calculations(api_client):
    employee = {
        "emp_code": "EMP9502",
        "name": "Monthly Calculation Test",
        "email": "analytics9502@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-10-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code == 201, created.text

    # October 2026: insert three weekdays and one weekend record.
    logs = [
        {
            "emp_code": "EMP9502",
            "date": "2026-10-01",  # Thursday: full presence
            "status": "PRESENT",
            "half_day": False,
            "late_minutes": 15,
            "overtime_minutes": 30,
        },
        {
            "emp_code": "EMP9502",
            "date": "2026-10-02",  # Friday: half-day presence
            "status": "WFH",
            "half_day": True,
            "late_minutes": 0,
            "overtime_minutes": 0,
        },
        {
            "emp_code": "EMP9502",
            "date": "2026-10-05",  # Monday: leave
            "status": "LEAVE",
            "half_day": False,
            "late_minutes": 0,
            "overtime_minutes": 0,
        },
        {
            "emp_code": "EMP9502",
            "date": "2026-10-03",  # Saturday: must not count as present
            "status": "PRESENT",
            "half_day": False,
            "late_minutes": 0,
            "overtime_minutes": 0,
        },
    ]

    from app.main import attendance_collection

    attendance_collection.insert_many(logs)

    response = api_client.get(
        "/analytics/employees/EMP9502/monthly",
        params={"month": "2026-10"},
    )

    assert response.status_code == 200, response.text
    result = response.json()

    assert result["working_days"] == 22
    assert result["present_days"] == 1.5
    assert result["leave_days"] == 1
    assert result["late_count"] == 1
    assert result["total_late_minutes"] == 15
    assert result["total_overtime_minutes"] == 30
    assert result["attendance_pct"] == 6.8182


def test_employee_monthly_analytics_invalid_month(api_client):
    response = api_client.get(
        "/analytics/employees/EMP9501/monthly",
        params={"month": "October-2026"},
    )

    assert response.status_code == 422

def test_department_summary_analytics_success(api_client):
    response = api_client.get(
        "/analytics/departments/summary",
        params={"month": "2026-10"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)

def test_late_arrival_leaderboard_success(api_client):
    response = api_client.get(
        "/analytics/leaderboard/late",
        params={"month": "2026-10", "limit": 10},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)

def test_department_trend_success(api_client):
    response = api_client.get(
        "/analytics/departments/Engineering/trend",
        params={
            "from": "2026-10-01",
            "to": "2026-10-07",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)

    # The trend must include every date in the requested range.
    assert len(data["items"]) == 7


def test_department_trend_returns_headcount_without_attendance_logs(api_client):
    from app.main import employees_collection, attendance_collection

    start_date = "2026-10-01"
    end_date = "2026-10-07"

    employee = {
        "emp_code": "EMP9801",
        "name": "Trend Regression Test",
        "email": "trend9801@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }
    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    # Count employees eligible for the requested period.
    eligible_employees = employees_collection.count_documents(
        {
            "department": "Engineering",
            "joined_on": {"$lte": end_date},
        }
    )

    assert eligible_employees > 0

    # Remove attendance records for this department's employees
    # during the requested date range.
    engineering_codes = employees_collection.distinct(
        "emp_code", {"department": "Engineering"}
    )
    attendance_collection.delete_many(
        {
            "emp_code": {"$in": engineering_codes},
            "date": {"$gte": start_date, "$lte": end_date},
        }
    )

    response = api_client.get(
        "/analytics/departments/Engineering/trend",
        params={"from": start_date, "to": end_date},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 7

    for item in items:
        assert item["headcount"] == eligible_employees
        assert item["present_count"] == 0
        assert item["late_count"] == 0



def test_admin_explain_attendance_list(api_client):
    response = api_client.get(
        "/admin/explain/attendance_list",
        params={"limit": 10, "skip": 0},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)

    # Explain output should contain MongoDB execution statistics.
    assert "executionStats" in str(data) or "executionStats" in data
def test_punch_in_rejects_epoch_seconds(api_client):
    employee = {
        "emp_code": "EMP9506",
        "name": "Timestamp Validation Test",
        "email": "overnight9506@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    # Epoch seconds should be rejected; the API requires epoch milliseconds.
    response = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9502",
            "punched_at": 1790895000,
            "status": "PRESENT",
        },
    )

    assert response.status_code == 422
def test_overnight_shift_punch_out(api_client):
    employee = {
        "emp_code": "EMP9503",
        "name": "Overnight Shift Test",
        "email": "overnight9503@example.com",
        "department": "Night Operations",
        "shift_start": "22:00",
        "shift_end": "06:00",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    # 22:00 IST on October 12, 2026.
    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9503",
            "punched_at": 1791822600000,
            "status": "PRESENT",
        },
    )
    assert punch_in.status_code in (200, 201)

    # 06:00 IST on October 13, 2026.
    punch_out = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9503",
            "punched_at": 1791851400000,
        },
    )
    assert punch_out.status_code == 200
def test_overnight_shift_calculates_eight_work_hours(api_client):
    employee = {
        "emp_code": "EMP9504",
        "name": "Overnight Hours Test",
        "email": "overnight9504@example.com",
        "department": "Night Operations",
        "shift_start": "22:00",
        "shift_end": "06:00",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9504",
            "punched_at": 1791822600000,
            "status": "PRESENT",
        },
    )

    punch_out = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9504",
            "punched_at": 1791851400000,
        },
    )
    assert punch_out.status_code == 200

    attendance = api_client.get(
        "/attendance",
        params={"emp_code": "EMP9504"},
    )
    assert attendance.status_code == 200

    records = attendance.json()["items"]
    assert len(records) == 1
    assert records[0]["work_hours"] == 8.0
def test_overtime_is_calculated_after_thirty_minutes(api_client):
    employee = {
        "emp_code": "EMP9505",
        "name": "Overtime Calculation Test",
        "email": "overtime9505@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9505",
            "punched_at": 1791864000000,
            "status": "PRESENT",
        },
    )
    assert punch_in.status_code in (200, 201)

    punch_out = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9505",
            "punched_at": 1791898200000,
        },
    )
    assert punch_out.status_code == 200

    attendance = api_client.get(
        "/attendance",
        params={"emp_code": "EMP9505"},
    )
    assert attendance.status_code == 200

    records = attendance.json()["items"]
    assert len(records) == 1
    assert records[0]["overtime_minutes"] == 30






def test_employee_rejects_identical_shift_start_and_end(api_client):
    employee = {
        "emp_code": "EMP9601",
        "name": "Invalid Shift Test",
        "email": "invalidshift9601@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "09:30",
        "joined_on": "2026-01-01",
    }

    response = api_client.post("/employees", json=employee)

    assert response.status_code == 422

    lookup = api_client.get(
        "/employees",
        params={"emp_code": "EMP9601"},
    )
    assert lookup.status_code == 200
    assert all(
        item["emp_code"] != "EMP9601"
        for item in lookup.json()["items"]
    )


def test_punch_out_at_punch_in_time_returns_422(api_client):
    employee = {
        "emp_code": "EMP9602",
        "name": "Invalid Punch Out Test",
        "email": "invalidpunch9602@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    punch_timestamp = 1791864000000

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP9602",
            "punched_at": punch_timestamp,
            "status": "PRESENT",
        },
    )
    assert punch_in.status_code in (200, 201)

    punch_out = api_client.post(
        "/attendance/punch-out",
        json={
            "emp_code": "EMP9602",
            "punched_at": punch_timestamp,
        },
    )

    assert punch_out.status_code == 422

def test_regularization_no_op_returns_422(api_client):
    employee = {
        "emp_code": "EMP9701",
        "name": "No Op Test",
        "email": "noop9701@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    punch_in_time = 1793439000000
    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9701",
        "punched_at": punch_in_time,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    response = api_client.patch("/attendance/EMP9701/2026-10-31", json={
        "status": "PRESENT",
        "reason": "No actual change",
        "regularized_by": "admin",
    })
    assert response.status_code == 422


def test_regularization_absent_with_punch_time_returns_422(api_client):
    employee = {
        "emp_code": "EMP9702",
        "name": "Absent Test",
        "email": "absent9702@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    punch_in_time = 1793439000000
    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9702",
        "punched_at": punch_in_time,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    response = api_client.patch("/attendance/EMP9702/2026-10-31", json={
        "status": "ABSENT",
        "punch_in": punch_in_time,
        "reason": "Testing invalid correction",
        "regularized_by": "admin",
    })
    assert response.status_code == 422


def test_regularization_missing_punch_in_returns_422(api_client):
    employee = {
        "emp_code": "EMP9703",
        "name": "Missing Punch Test",
        "email": "missingpunch9703@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    response = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9703",
        "punched_at": 1793439000000,
        "status": "PRESENT",
    })
    assert response.status_code in (200, 201)

    correction = api_client.patch("/attendance/EMP9703/2026-10-31", json={
        "status": "LEAVE",
        "reason": "Convert to leave",
        "regularized_by": "admin",
    })
    assert correction.status_code in (200, 201)

    # A presence status cannot be restored without a punch-in.
    response = api_client.patch("/attendance/EMP9703/2026-10-31", json={
        "status": "PRESENT",
        "reason": "Restore presence",
        "regularized_by": "admin",
    })
    assert response.status_code == 422


def test_regularization_history_records_only_changed_fields(api_client):
    employee = {
        "emp_code": "EMP9704",
        "name": "Audit History Test",
        "email": "history9704@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    punch_in_time = 1793439000000
    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9704",
        "punched_at": punch_in_time,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    corrected_time = punch_in_time + 60000
    response = api_client.patch("/attendance/EMP9704/2026-10-31", json={
        "punch_in": corrected_time,
        "reason": "Correct punch-in time",
        "regularized_by": "admin",
    })
    assert response.status_code == 200, response.text

    record = response.json()
    assert len(record["history"]) == 1
    entry = record["history"][0]
    assert entry["by"] == "admin"
    assert entry["reason"] == "Correct punch-in time"
    assert set(entry["changes"].keys()) == {"punch_in"}

def test_regularization_unknown_employee_returns_404(api_client):
    response = api_client.patch("/attendance/EMP9791/2026-10-31", json={
        "status": "LEAVE",
        "reason": "Test unknown employee",
        "regularized_by": "admin",
    })
    assert response.status_code == 404


def test_regularization_missing_record_returns_404(api_client):
    employee = {
        "emp_code": "EMP9792",
        "name": "Missing Record Test",
        "email": "missingrecord9792@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201)

    response = api_client.patch("/attendance/EMP9792/2026-10-31", json={
        "status": "LEAVE",
        "reason": "Test missing record",
        "regularized_by": "admin",
    })
    assert response.status_code == 404


def test_regularization_wrong_attendance_date_returns_422(api_client):
    employee = {
        "emp_code": "EMP9793",
        "name": "Wrong Date Test",
        "email": "wrongdate9793@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9793",
        "punched_at": 1793439000000,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    response = api_client.patch("/attendance/EMP9793/2026-10-31", json={
        "punch_in": 1793525400000,
        "reason": "Test wrong attendance date",
        "regularized_by": "admin",
    })
    assert response.status_code == 422


def test_regularization_clears_times_when_status_becomes_leave(api_client):
    employee = {
        "emp_code": "EMP9794",
        "name": "Leave Correction Test",
        "email": "leave9794@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    punch_in_time = 1793439000000
    punch_out_time = punch_in_time + 9 * 60 * 60 * 1000

    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9794",
        "punched_at": punch_in_time,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    punched_out = api_client.post("/attendance/punch-out", json={
        "emp_code": "EMP9794",
        "punched_at": punch_out_time,
    })
    assert punched_out.status_code == 200, punched_out.text

    response = api_client.patch("/attendance/EMP9794/2026-10-31", json={
        "status": "LEAVE",
        "reason": "Approved leave",
        "regularized_by": "admin",
    })
    assert response.status_code == 200, response.text

    record = response.json()
    assert record["status"] == "LEAVE"
    assert record["punch_in"] is None
    assert record["punch_out"] is None
    assert record["work_hours"] == 0
    assert record["overtime_minutes"] == 0
    assert record["half_day"] is False


def test_regularization_punch_out_before_punch_in_returns_422(api_client):
    employee = {
        "emp_code": "EMP9795",
        "name": "Invalid Time Correction",
        "email": "invalidtime9795@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }
    assert api_client.post("/employees", json=employee).status_code in (200, 201)

    punch_in_time = 1793439000000
    created = api_client.post("/attendance/punch-in", json={
        "emp_code": "EMP9795",
        "punched_at": punch_in_time,
        "status": "PRESENT",
    })
    assert created.status_code in (200, 201)

    response = api_client.patch("/attendance/EMP9795/2026-10-31", json={
        "punch_out": punch_in_time - 60000,
        "reason": "Test invalid punch-out",
        "regularized_by": "admin",
    })
    assert response.status_code == 422

def test_concurrent_punch_in_only_one_request_succeeds(api_client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    employee = {
        "emp_code": "EMP9796",
        "name": "Concurrent Punch Test",
        "email": "concurrent9796@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201), created.text

    barrier = Barrier(2)
    punch_payload = {
        "emp_code": "EMP9796",
        "punched_at": 1793439000000,
        "status": "PRESENT",
    }

    def send_punch_in():
        barrier.wait(timeout=10)
        return api_client.post("/attendance/punch-in", json=punch_payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(send_punch_in),
            executor.submit(send_punch_in),
        ]
        responses = [future.result(timeout=20) for future in futures]

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409], [
        (response.status_code, response.text)
        for response in responses
    ]
def test_employee_list_is_sorted_by_emp_code(api_client):
    for code in ["EMP0003", "EMP0001", "EMP0002"]:
        response = api_client.post(
            "/employees",
            json={
                "emp_code": code,
                "name": f"Employee {code}",
                "email": f"{code.lower()}@example.com",
                "department": "Engineering",
                "joined_on": "2026-01-01",
            },
        )
        assert response.status_code == 201

    response = api_client.get("/employees?page_size=100")

    assert response.status_code == 200
    codes = [item["emp_code"] for item in response.json()["items"]]
    assert codes == sorted(codes)


def test_employee_list_department_filter_has_correct_total(api_client):
    department = "FilterTestDepartment"

    employees = [
        ("EMP8101", department),
        ("EMP8102", department),
        ("EMP8103", "OtherTestDepartment"),
    ]

    for code, employee_department in employees:
        response = api_client.post(
            "/employees",
            json={
                "emp_code": code,
                "name": f"Employee {code}",
                "email": f"{code.lower()}@example.com",
                "department": employee_department,
                "joined_on": "2026-01-01",
            },
        )
        assert response.status_code == 201, f"Failed code: {code}; response: {response.text}"

    response = api_client.get(
        f"/employees?department={department}&page_size=100"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(
        item["department"] == department
        for item in body["items"]
    )



def test_employee_list_pagination_returns_correct_metadata(api_client):
    department = "PaginationTestDepartment"

    employees = [
    ("EMP991001", "pagination1"),
    ("EMP991002", "pagination2"),
    ("EMP991003", "pagination3"),
    ("EMP991004", "pagination4"),
]

    for code, email_prefix in employees:
        response = api_client.post(
            "/employees",
            json={
                "emp_code": code,
                "name": f"Employee {code}",
                "email": f"{email_prefix}@example.com",
                "department": department,
                "joined_on": "2026-01-01",
            },
        )
        assert response.status_code == 201, response.text

    response = api_client.get(
        "/employees",
        params={
            "department": department,
            "page": 1,
            "page_size": 2,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
def test_attendance_date_range_filter_is_inclusive(api_client):
    employee = {
        "emp_code": "EMP992001",
        "name": "Date Filter Test",
        "email": "datefilter992001@example.com",
        "department": "AttendanceFilterTests",
        "joined_on": "2026-01-01",
    }
    created = api_client.post("/employees", json=employee)
    assert created.status_code == 201, created.text

    timestamps = [
    1793332800000,  # 2026-10-30, 09:30 IST
    1793419200000,  # 2026-10-31, 09:30 IST
    1793505600000,  # 2026-11-01, 09:30 IST
]

    for timestamp in timestamps:
        response = api_client.post(
            "/attendance/punch-in",
            json={
                "emp_code": "EMP992001",
                "punched_at": timestamp,
                "status": "PRESENT",
            },
        )
        assert response.status_code in (200, 201), response.text

    response = api_client.get(
        "/attendance",
        params={
            "emp_code": "EMP992001",
            "date_from": "2026-10-30",
            "date_to": "2026-10-31",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    dates = [item["date"] for item in data["items"]]

    assert data["total"] == 2
    assert set(dates) == {"2026-10-30", "2026-10-31"}


def test_attendance_invalid_date_range_returns_422(api_client):
    response = api_client.get(
        "/attendance",
        params={
            "date_from": "2026-11-02",
            "date_to": "2026-11-01",
        },
    )

    assert response.status_code == 422


def test_attendance_invalid_status_returns_422(api_client):
    response = api_client.get(
        "/attendance",
        params={"status": "INVALID_STATUS"},
    )

    assert response.status_code == 422
def test_attendance_filter_by_status(api_client):
    employee = {
        "emp_code": "EMP993001",
        "name": "Status Filter Test",
        "email": "status993001@example.com",
        "department": "AttendanceFilterTests",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201), created.text

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP993001",
            "punched_at": 1793332800000,
            "status": "WFH",
        },
    )
    assert punch_in.status_code in (200, 201), punch_in.text

    response = api_client.get(
        "/attendance",
        params={"status": "WFH"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    assert any(
        item["emp_code"] == "EMP993001" and item["status"] == "WFH"
        for item in data["items"]
    )


def test_attendance_combined_employee_and_date_filters(api_client):
    employee = {
        "emp_code": "EMP993002",
        "name": "Combined Filter Test",
        "email": "combined993002@example.com",
        "department": "AttendanceFilterTests",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201), created.text

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP993002",
            "punched_at": 1793332800000,
            "status": "PRESENT",
        },
    )
    assert punch_in.status_code in (200, 201), punch_in.text

    response = api_client.get(
        "/attendance",
        params={
            "emp_code": "EMP993002",
            "date_from": "2026-10-30",
            "date_to": "2026-10-30",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["emp_code"] == "EMP993002"
    assert data["items"][0]["date"] == "2026-10-30"


def test_attendance_pagination_metadata(api_client):
    response = api_client.get(
        "/attendance",
        params={"page": 1, "page_size": 2},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2
    assert isinstance(data["total"], int)
    assert data["total"] >= len(data["items"])
def test_concurrent_punch_out_only_one_request_succeeds(api_client):
    from concurrent.futures import ThreadPoolExecutor

    employee = {
        "emp_code": "EMP994001",
        "name": "Concurrent Punch Out Test",
        "email": "concurrent994001@example.com",
        "department": "ConcurrencyTests",
        "joined_on": "2026-01-01",
    }

    created = api_client.post("/employees", json=employee)
    assert created.status_code in (200, 201), created.text

    punch_in_time = 1793332800000
    punch_out_time = punch_in_time + 9 * 60 * 60 * 1000

    punch_in = api_client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP994001",
            "punched_at": punch_in_time,
            "status": "PRESENT",
        },
    )
    assert punch_in.status_code in (200, 201), punch_in.text

    def send_punch_out():
        return api_client.post(
            "/attendance/punch-out",
            json={
                "emp_code": "EMP994001",
                "punched_at": punch_out_time,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(send_punch_out),
            executor.submit(send_punch_out),
        ]
        responses = [future.result() for future in futures]

    status_codes = sorted(response.status_code for response in responses)

    assert status_codes == [200, 409], [
        (response.status_code, response.text)
        for response in responses
    ]
