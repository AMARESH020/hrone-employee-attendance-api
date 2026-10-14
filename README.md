# Employee Attendance & Analytics API

A FastAPI and MongoDB API for employee management, attendance tracking, regularization, and analytics.

## Requirements

- Python 3.10 or newer
- MongoDB 6.0 or newer

## Run locally on Windows

From the repository root, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:MONGO_URI = "mongodb://localhost:27017"
$env:MONGO_DB = "attendance_db"

uvicorn app.main:app --port 8000
```

Ensure MongoDB is running first. Indexes are created at application startup.

- Health check: `http://localhost:8000/health`
- Interactive API documentation: `http://localhost:8000/docs`

## Tests

```powershell
python -m pytest -q
```

## Submission safety

Do not commit secrets, local environment files, virtual environments, confidential assignment materials, or sample-data dumps.
