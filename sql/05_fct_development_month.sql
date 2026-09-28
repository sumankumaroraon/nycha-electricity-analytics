-- 05_fct_development_month.sql
-- Development (TDS #) x revenue month on a COMPLETE monthly panel: months with no bills are kept
-- as rows with is_missing_month = true so gaps stay visible in reporting.

CREATE OR REPLACE TABLE fct_development_month AS
WITH agg AS (
    SELECT
        tds,
        revenue_month,
        sum(kwh)                                         AS kwh,
        sum(current_charges)                             AS cost,
        sum(kw)                                          AS kw,
        sum(kwh_charges)                                 AS kwh_charges,
        sum(kw_charges)                                  AS kw_charges,
        sum(other_charges)                               AS other_charges,
        sum(CASE WHEN current_charges < 0 THEN current_charges ELSE 0 END) AS credits,
        count(*)                                         AS n_records,
        count(DISTINCT meter_number)                     AS n_meters,
        count(*) FILTER (flag_estimated)                 AS n_estimated,
        count(*) FILTER (flag_negative_cost)             AS n_negative_cost,
        count(*) FILTER (flag_demand_only)               AS n_demand_only,
        count(*) FILTER (flag_extreme_rate_high OR flag_extreme_rate_low) AS n_extreme_rate,
        count(*) FILTER (flag_bill_exception)            AS n_bill_exception,
        arg_max(record_id, abs(current_charges))         AS top_record_id
    FROM int_bills_flagged
    GROUP BY tds, revenue_month
), dims AS (
    SELECT tds,
           arg_max(development_name, revenue_month) AS development_name,
           arg_max(borough, revenue_month)          AS borough
    FROM int_bills_flagged
    GROUP BY tds
), months AS (
    SELECT CAST(m AS DATE) AS revenue_month
    FROM analysis_window w, generate_series(w.window_start, w.window_end, INTERVAL 1 MONTH) g(m)
), panel AS (
    SELECT d.tds, d.development_name, d.borough, m.revenue_month
    FROM dims d CROSS JOIN months m
), joined AS (
    SELECT p.*, a.* EXCLUDE (tds, revenue_month),
           a.n_records IS NULL AS is_missing_month
    FROM panel p LEFT JOIN agg a USING (tds, revenue_month)
), typical AS (
    SELECT tds, median(n_meters) AS typical_meters
    FROM joined WHERE NOT is_missing_month GROUP BY tds
)
SELECT
    j.tds, j.development_name, j.borough, j.revenue_month,
    year(j.revenue_month)  AS year,
    month(j.revenue_month) AS month,
    j.kwh, j.cost, j.kw, j.kwh_charges, j.kw_charges, j.other_charges, j.credits,
    coalesce(j.n_records, 0)        AS n_records,
    coalesce(j.n_meters, 0)         AS n_meters,
    coalesce(j.n_estimated, 0)      AS n_estimated,
    coalesce(j.n_negative_cost, 0)  AS n_negative_cost,
    coalesce(j.n_demand_only, 0)    AS n_demand_only,
    coalesce(j.n_extreme_rate, 0)   AS n_extreme_rate,
    coalesce(j.n_bill_exception, 0) AS n_bill_exception,
    j.top_record_id,
    j.is_missing_month,
    j.kwh / 1000.0                                          AS mwh,
    CASE WHEN j.kwh > 0 THEN j.cost / j.kwh END             AS effective_cost_per_kwh,
    t.typical_meters,
    (NOT j.is_missing_month AND abs(coalesce(j.n_meters, 0) / t.typical_meters - 1) > 0.10) AS flag_meter_count_change
FROM joined j
LEFT JOIN typical t USING (tds)
ORDER BY j.tds, j.revenue_month;
