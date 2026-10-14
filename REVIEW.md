# Code Review

## Scope and evidence

The implementation was tested with `python -m pytest -q`: **47 tests passed**. The findings below distinguish behavior verified by regression tests from defects that still require a reproducible comparison against the original starter. Test coverage does not prove that every business rule or input has been tested.

## Verified regression coverage

| Area | Evidence | Verified behavior |
|---|---|---|
| Employee creation | `test_create_employee_success`, `test_duplicate_employee_code_returns_conflict`, `test_invalid_employee_code_is_rejected` | Successful creation, duplicate-code conflict, and invalid-code rejection |
| Punch-in and punch-out | `test_attendance_punch_in_success`, `test_attendance_punch_out_success`, `test_punch_in_unknown_employee_returns_404`, `test_punch_out_without_punch_in_returns_404` | Successful punches and expected missing-employee or missing-punch responses |
| Concurrency | `test_concurrent_punch_in_only_one_request_succeeds`, `test_concurrent_punch_out_only_one_request_succeeds` | Concurrent requests are checked to ensure only one succeeds in each tested scenario |
| Regularization | `test_attendance_regularization_requires_reason`, `test_successful_regularization_records_history`, `test_regularization_history_records_only_changed_fields` | Reason validation, change history, and recording only changed fields |
| Regularization validation | `test_regularization_no_op_returns_422`, `test_regularization_missing_record_returns_404`, `test_regularization_punch_out_before_punch_in_returns_422` | Tested no-op, missing-record, and invalid time-order handling |
| Attendance filtering | `test_attendance_date_range_filter_is_inclusive`, `test_attendance_invalid_date_range_returns_422`, `test_attendance_invalid_status_returns_422`, `test_attendance_combined_employee_and_date_filters` | Inclusive date filtering, invalid-range and status rejection, and combined filters |
| Pagination | `test_employee_list_pagination_returns_correct_metadata`, `test_attendance_pagination_metadata` | Pagination metadata for employee and attendance lists |
| Monthly analytics | `test_employee_monthly_analytics_success`, `test_employee_monthly_analytics_calculations`, `test_department_summary_analytics_success` | Tested monthly calculations and department summary behavior |
| Leaderboard | `test_late_arrival_leaderboard_success` | Successful leaderboard response; cutoff-tie behavior is not established by this test name alone |
| Department trend | `test_department_trend_success`, `test_department_trend_returns_headcount_without_attendance_logs` | Trend response and a no-attendance-log case that checks daily rows and headcount |
| Query explanation | `test_admin_explain_attendance_list` | Successful explain response for the attendance-list operation |

## Additional attendance rules tested

- Overnight shift punch-out and work-hour calculation.
- Overtime calculation after the configured threshold.
- Rejection of identical shift start and end times.
- Rejection of epoch-second punch-in values.
- Rejection of punch-out times equal to or earlier than punch-in.
- Regularization rules for absent and leave statuses, missing punch times, and unknown employees.

## Original-starter defect inventory

### 1. Department trend passes Python date objects to MongoDB

- **Location:** `department_attendance_trend()` in the original `main.py`, around line 2799.
- **Problem:** The validated `start_date` and `end_date` values are Python `date` objects. The aggregation uses them as comparison values, which PyMongo cannot encode in this context.
- **How it was found:** Ran `test_department_trend_returns_headcount_without_attendance_logs` against an isolated copy of the original starter. The request failed with `bson.errors.InvalidDocument`, identifying a `datetime.date` value that could not be encoded.
- **Fix:** Convert both dates to ISO-formatted strings with `.isoformat()` before using them in MongoDB filters.
- **Verification:** After applying this correction to the isolated copy, the targeted regression test passed. This verifies the date-encoding fix for that test; it does not establish that every department-trend behavior is correct.
## Query-plan verification

The application includes an explain endpoint using MongoDB `executionStats`. This review does not claim that the required `IXSCAN` and absence of `COLLSCAN` have been verified against a representative 100,000-record dataset. That requires a live MongoDB explain-plan check.
