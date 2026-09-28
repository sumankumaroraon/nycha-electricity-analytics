-- 08_reconcile_with_python.sql
-- Independent cross-check: the SQL and Python layers implement the same rules separately.
-- Requires the Python pipeline outputs in data/processed/. Each row counts mismatches.

WITH py_dm AS (
    SELECT * FROM read_csv(getvariable('processed_dir') || '/fact_development_month.csv', auto_detect = true)
),
py_ex AS (
    SELECT * FROM read_csv(getvariable('processed_dir') || '/exclusion_log.csv', auto_detect = true)
),
r01 AS (
    SELECT 'R01' AS check_id, 'Development-month kWh and cost match Python (tolerance $0.01 / 0.01 kWh)' AS description,
           count(*) AS mismatches
    FROM fct_development_month s
    FULL OUTER JOIN py_dm p ON s.tds = p.tds AND s.revenue_month = CAST(p.revenue_month AS DATE)
    WHERE s.tds IS NULL OR p.tds IS NULL
       OR abs(coalesce(s.cost, 0) - coalesce(p.cost, 0)) > 0.01
       OR abs(coalesce(s.kwh, 0)  - coalesce(p.kwh, 0))  > 0.01
       OR s.n_meters <> p.n_meters
       OR s.is_missing_month <> p.is_missing_month
       OR s.flag_meter_count_change <> p.flag_meter_count_change
),
r02 AS (
    SELECT 'R02', 'Same excluded record_ids and reasons as Python',
           count(*)
    FROM int_exclusion_log s
    FULL OUTER JOIN py_ex p ON s.record_id = p.record_id AND s.reason = p.reason
    WHERE s.record_id IS NULL OR p.record_id IS NULL
),
r03 AS (
    SELECT 'R03', 'record_id points to the same source row in both layers (sampled fields)',
           count(*)
    FROM int_exclusion_log s JOIN py_ex p USING (record_id)
    WHERE s.meter_number IS DISTINCT FROM CAST(p.meter_number AS VARCHAR)
       OR abs(coalesce(s.current_charges, 0) - coalesce(p.current_charges, 0)) > 0.01
)
SELECT * FROM r01 UNION ALL SELECT * FROM r02 UNION ALL SELECT * FROM r03 ORDER BY check_id;
