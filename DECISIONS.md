# Implementation Decisions

1. **Indexes.** The implementation creates seven indexes: unique indexes on `employees.emp_code` and `attendance_logs(emp_code, date)`, plus supporting indexes for department lookups, joining-date headcount queries, attendance date ranges, punch-in history, and status/date filtering. A punch-out index could be added if query profiling demonstrated a benefit.

2. **Simultaneous punch-ins.** Two requests can both pass the employee lookup, but the unique employee/date index allows only one attendance record for that employee and date. The losing insert should be handled as a duplicate-key conflict and returned as HTTP 409.

3. **Leaderboard ties.** The late-arrival leaderboard uses MongoDB `$rank` and includes employees whose rank is at or below the requested limit. Employees tied at the cutoff therefore share the rank and may cause the response to contain more rows than the limit.

4. **Department headcount.** The department summary starts from employees and joins attendance records using `$lookup` with `preserveNullAndEmptyArrays`. Employees without attendance logs remain represented in the result and count toward headcount.

5. **At 100× scale.** I would inspect query plans and workload metrics, validate index use with representative data, and profile expensive aggregations. If live analytics became too costly, I would consider pre-aggregated summaries and background refreshes while preserving the required API behavior.
