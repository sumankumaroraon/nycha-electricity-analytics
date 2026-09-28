-- 03_int_bills_deduplicated.sql
-- Two exclusion rules only:
--   1. exact_duplicate: every source field identical to an earlier record.
--   2. superseded_bill / near_duplicate_same_bill: same development, meter, revenue month and
--      service period as another record; keep the highest UMIS BILL ID (latest issue).
-- Everything excluded is written to int_exclusion_log with its reason.

CREATE OR REPLACE TABLE int_window_bills AS
SELECT s.*
FROM stg_bills s, analysis_window w
WHERE s.revenue_month BETWEEN w.window_start AND w.window_end;

CREATE OR REPLACE TABLE int_exact_ranked AS
SELECT *,
    row_number() OVER (
        PARTITION BY development_name, borough, account_name, location, meter_amr, meter_scope, tds, edp,
                     rc_code, funding_source, amp, vendor_name, umis_bill_id, revenue_month, service_start,
                     service_end, service_days, meter_number, estimated, current_charges, rate_class,
                     bill_analyzed, kwh, kwh_charges, kw, kw_charges, other_charges
        ORDER BY record_id) AS exact_rank
FROM int_window_bills;

CREATE OR REPLACE TABLE int_version_ranked AS
SELECT *,
    row_number() OVER (
        PARTITION BY tds, meter_number, revenue_month, service_start, service_end
        ORDER BY umis_bill_id DESC, record_id) AS version_rank,
    max(umis_bill_id) OVER (PARTITION BY tds, meter_number, revenue_month, service_start, service_end) AS max_bill_id,
    count(*)          OVER (PARTITION BY tds, meter_number, revenue_month, service_start, service_end) AS n_versions_same_period
FROM int_exact_ranked
WHERE exact_rank = 1;

CREATE OR REPLACE TABLE int_exclusion_log AS
SELECT record_id, tds, development_name, meter_number, revenue_month, umis_bill_id, kwh, current_charges,
       'exact_duplicate' AS reason
FROM int_exact_ranked WHERE exact_rank > 1
UNION ALL
SELECT record_id, tds, development_name, meter_number, revenue_month, umis_bill_id, kwh, current_charges,
       CASE WHEN umis_bill_id < max_bill_id THEN 'superseded_bill' ELSE 'near_duplicate_same_bill' END
FROM int_version_ranked WHERE version_rank > 1;

CREATE OR REPLACE TABLE int_bills_deduplicated AS
SELECT * EXCLUDE (exact_rank, version_rank, max_bill_id)
FROM int_version_ranked
WHERE version_rank = 1;
