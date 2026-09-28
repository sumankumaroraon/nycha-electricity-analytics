-- 06_mart_metrics_and_drivers.sql
-- Business metrics. Ratios are always aggregate dollars / aggregate kWh, never averages of ratios.

-- Annual portfolio metrics with year-over-year change.
CREATE OR REPLACE TABLE mart_annual AS
WITH a AS (
    SELECT year,
           sum(kwh)            AS kwh,
           sum(kwh) / 1000.0   AS mwh,
           sum(cost)           AS cost,
           sum(cost) / nullif(sum(kwh), 0) AS effective_cost_per_kwh
    FROM fct_development_month
    GROUP BY year
)
SELECT *,
       kwh  / lag(kwh)  OVER (ORDER BY year) - 1                                        AS kwh_yoy,
       cost / lag(cost) OVER (ORDER BY year) - 1                                        AS cost_yoy,
       effective_cost_per_kwh / lag(effective_cost_per_kwh) OVER (ORDER BY year) - 1    AS rate_yoy
FROM a
ORDER BY year;

-- Development x year: YoY and share of portfolio spending.
CREATE OR REPLACE TABLE mart_development_year AS
WITH d AS (
    SELECT tds, development_name, borough, year,
           sum(kwh) AS kwh, sum(cost) AS cost,
           count(*) FILTER (NOT is_missing_month) AS months_reported
    FROM fct_development_month
    GROUP BY ALL
)
SELECT *,
       cost / nullif(kwh, 0)                                                                AS effective_cost_per_kwh,
       kwh  / nullif(lag(kwh)  OVER (PARTITION BY tds ORDER BY year), 0) - 1                AS kwh_yoy,
       cost / nullif(lag(cost) OVER (PARTITION BY tds ORDER BY year), 0) - 1                AS cost_yoy,
       cost / sum(cost) OVER (PARTITION BY year)                                            AS share_of_portfolio_cost,
       row_number() OVER (PARTITION BY year ORDER BY cost DESC)                             AS cost_rank_in_year
FROM d;

-- Same-month YoY decomposition:
--   consumption_effect = (Q1 - Q0) * R0 ;  rate_effect = Q1 * (R1 - R0)
-- Defined only when both months have kWh > 0; otherwise the change is "non_comparable".
CREATE OR REPLACE TABLE mart_cost_decomposition AS
WITH cur AS (SELECT * FROM fct_development_month WHERE year > getvariable('start_year')),
pairs AS (
    SELECT c.tds, c.development_name, c.borough, c.year, c.month, c.revenue_month,
           coalesce(p.kwh, 0)  AS kwh_pri,  coalesce(p.cost, 0) AS cost_pri,
           coalesce(c.kwh, 0)  AS kwh_cur,  coalesce(c.cost, 0) AS cost_cur
    FROM cur c
    LEFT JOIN fct_development_month p
      ON p.tds = c.tds AND p.year = c.year - 1 AND p.month = c.month
)
SELECT *,
       (kwh_cur > 0 AND kwh_pri > 0)                                         AS comparable,
       cost_cur - cost_pri                                                   AS cost_change,
       CASE WHEN kwh_cur > 0 AND kwh_pri > 0
            THEN (kwh_cur - kwh_pri) * (cost_pri / kwh_pri) ELSE 0 END       AS consumption_effect,
       CASE WHEN kwh_cur > 0 AND kwh_pri > 0
            THEN kwh_cur * (cost_cur / kwh_cur - cost_pri / kwh_pri) ELSE 0 END AS rate_effect,
       CASE WHEN kwh_cur > 0 AND kwh_pri > 0 THEN 0
            ELSE cost_cur - cost_pri END                                     AS non_comparable_change
FROM pairs;

-- Portfolio bridge per year (feeds the waterfall).
CREATE OR REPLACE TABLE mart_cost_bridge AS
SELECT year,
       sum(cost_pri)              AS prior_cost,
       sum(consumption_effect)    AS consumption_effect,
       sum(rate_effect)           AS rate_effect,
       sum(non_comparable_change) AS non_comparable_change,
       sum(cost_cur)              AS current_cost
FROM mart_cost_decomposition
GROUP BY year
ORDER BY year;
