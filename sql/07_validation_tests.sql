-- 07_validation_tests.sql
-- Each test counts FAILING rows. The runner fails the build if any count is non-zero.

WITH
t01 AS (  -- Row flow reconciles: raw = outside window + excluded + retained
    SELECT 'T01' AS test_id, 'Row counts reconcile across the pipeline' AS description,
           CASE WHEN (SELECT count(*) FROM raw_bills)
                   = (SELECT count(*) FROM stg_bills s, analysis_window w
                      WHERE s.revenue_month NOT BETWEEN w.window_start AND w.window_end OR s.revenue_month IS NULL)
                   + (SELECT count(*) FROM int_exclusion_log)
                   + (SELECT count(*) FROM int_bills_flagged)
                THEN 0 ELSE 1 END AS failures
),
t02 AS (
    SELECT 'T02', 'fct_development_month is unique on (tds, revenue_month)',
           count(*) FROM (SELECT tds, revenue_month FROM fct_development_month GROUP BY ALL HAVING count(*) > 1)
),
t03 AS (
    SELECT 'T03', 'Bill components sum to current charges (tolerance $0.01)',
           count(*) FROM int_bills_flagged
           WHERE abs(current_charges - (kwh_charges + kw_charges + other_charges)) > 0.01
),
t04 AS (
    SELECT 'T04', 'Fact totals equal retained record totals',
           CASE WHEN abs((SELECT sum(cost) FROM fct_development_month) - (SELECT sum(current_charges) FROM int_bills_flagged)) < 0.01
                 AND abs((SELECT sum(kwh)  FROM fct_development_month) - (SELECT sum(kwh) FROM int_bills_flagged)) < 0.01
                THEN 0 ELSE 1 END
),
t05 AS (
    SELECT 'T05', 'Decomposition effects sum to the cost change on every row',
           count(*) FROM mart_cost_decomposition
           WHERE abs(consumption_effect + rate_effect + non_comparable_change - cost_change) > 0.01
),
t06 AS (
    SELECT 'T06', 'Portfolio bridge closes for every year',
           count(*) FROM mart_cost_bridge
           WHERE abs(prior_cost + consumption_effect + rate_effect + non_comparable_change - current_cost) > 0.01
),
t07 AS (
    SELECT 'T07', 'No excluded record is also retained',
           count(*) FROM int_exclusion_log e JOIN int_bills_flagged f USING (record_id)
),
t08 AS (
    SELECT 'T08', 'Retained records are unique on (tds, meter, revenue month, service period)',
           count(*) FROM (SELECT tds, meter_number, revenue_month, service_start, service_end
                          FROM int_bills_flagged GROUP BY ALL HAVING count(*) > 1)
),
t09 AS (
    SELECT 'T09', 'Every retained record has a revenue month and a development ID',
           count(*) FROM int_bills_flagged WHERE revenue_month IS NULL OR tds IS NULL
),
t10 AS (
    SELECT 'T10', 'Effective cost is only defined where kWh > 0',
           count(*) FROM fct_development_month
           WHERE (effective_cost_per_kwh IS NOT NULL) <> coalesce(kwh > 0, false)
)
SELECT * FROM t01 UNION ALL SELECT * FROM t02 UNION ALL SELECT * FROM t03 UNION ALL SELECT * FROM t04
UNION ALL SELECT * FROM t05 UNION ALL SELECT * FROM t06 UNION ALL SELECT * FROM t07 UNION ALL SELECT * FROM t08
UNION ALL SELECT * FROM t09 UNION ALL SELECT * FROM t10
ORDER BY test_id;
