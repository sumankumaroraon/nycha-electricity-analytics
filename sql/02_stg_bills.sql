-- 02_stg_bills.sql
-- Standardise names, types and dates. No rows are removed here.

-- Same text rule as the Python layer: trim and collapse internal whitespace.
CREATE OR REPLACE MACRO clean_text(x) AS nullif(regexp_replace(trim(x), '\s+', ' ', 'g'), '');

CREATE OR REPLACE TABLE stg_bills AS
SELECT
    record_id,
    upper(clean_text("Development Name"))                          AS development_name,
    upper(clean_text("Borough"))                                   AS borough,
    clean_text("Account Name")                                     AS account_name,
    clean_text("Location")                                         AS location,
    clean_text("Meter AMR")                                        AS meter_amr,
    clean_text("Meter Scope")                                      AS meter_scope,
    TRY_CAST("TDS #" AS INTEGER)                                   AS tds,
    clean_text("EDP")                                              AS edp,
    clean_text("RC Code")                                          AS rc_code,
    clean_text("Funding Source")                                   AS funding_source,
    clean_text("AMP #")                                            AS amp,
    clean_text("Vendor Name")                                      AS vendor_name,
    TRY_CAST("UMIS BILL ID" AS BIGINT)                             AS umis_bill_id,
    TRY_CAST(try_strptime("Revenue Month", '%Y-%m') AS DATE)       AS revenue_month,
    TRY_CAST(try_strptime("Service Start Date", '%m/%d/%Y') AS DATE) AS service_start,
    TRY_CAST(try_strptime("Service End Date", '%m/%d/%Y') AS DATE)   AS service_end,
    TRY_CAST(replace("# days", ',', '') AS DOUBLE)                 AS service_days,
    clean_text("Meter Number")                                     AS meter_number,
    clean_text("Estimated")                                        AS estimated,
    TRY_CAST(replace("Current Charges", ',', '') AS DOUBLE)        AS current_charges,
    clean_text("Rate Class")                                       AS rate_class,
    clean_text("Bill Analyzed")                                    AS bill_analyzed,
    TRY_CAST(replace("Consumption (KWH)", ',', '') AS DOUBLE)      AS kwh,
    TRY_CAST(replace("KWH Charges", ',', '') AS DOUBLE)            AS kwh_charges,
    TRY_CAST(replace("Consumption (KW)", ',', '') AS DOUBLE)       AS kw,
    TRY_CAST(replace("KW Charges", ',', '') AS DOUBLE)             AS kw_charges,
    TRY_CAST(replace("Other charges", ',', '') AS DOUBLE)          AS other_charges
FROM raw_bills;

-- Analysis window: START_YEAR through the last calendar year with all 12 revenue months present.
CREATE OR REPLACE TABLE analysis_window AS
WITH months AS (
    SELECT DISTINCT revenue_month FROM stg_bills WHERE revenue_month IS NOT NULL
), complete_years AS (
    SELECT year(revenue_month) AS yr FROM months GROUP BY 1 HAVING count(*) = 12
)
SELECT
    make_date(getvariable('start_year'), 1, 1)                                   AS window_start,
    make_date(coalesce(getvariable('end_year'), (SELECT max(yr) FROM complete_years)), 12, 1) AS window_end,
    coalesce(getvariable('end_year'), (SELECT max(yr) FROM complete_years))      AS end_year;
