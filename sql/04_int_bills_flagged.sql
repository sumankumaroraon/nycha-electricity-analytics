-- 04_int_bills_flagged.sql
-- Quality flags. Flagged records are RETAINED; flags describe, they do not exclude.

CREATE OR REPLACE TABLE int_rate_bounds AS
SELECT
    quantile_cont(current_charges / kwh, 0.005) AS rate_lo,
    quantile_cont(current_charges / kwh, 0.995) AS rate_hi
FROM int_bills_deduplicated
WHERE kwh > 0 AND current_charges > 0;

CREATE OR REPLACE TABLE int_bills_flagged AS
SELECT
    b.*,
    CASE WHEN b.kwh > 0 AND b.current_charges > 0 THEN b.current_charges / b.kwh END  AS row_rate,
    (b.kwh = 0 AND b.current_charges > 0)                                              AS flag_zero_kwh_positive_cost,
    (b.kwh = 0 AND b.current_charges > 0 AND b.kw > 0)                                 AS flag_demand_only,
    (b.kwh = 0 AND b.current_charges = 0)                                              AS flag_zero_kwh_zero_cost,
    (b.current_charges < 0)                                                            AS flag_negative_cost,
    (b.kwh < 0)                                                                        AS flag_negative_kwh,
    coalesce(b.kwh > 0 AND b.current_charges > 0 AND b.current_charges / b.kwh > r.rate_hi, false) AS flag_extreme_rate_high,
    coalesce(b.kwh > 0 AND b.current_charges > 0 AND b.current_charges / b.kwh < r.rate_lo, false) AS flag_extreme_rate_low,
    coalesce(b.estimated = 'Y', false)                                                 AS flag_estimated,
    coalesce(b.bill_analyzed = 'Exception', false)                                     AS flag_bill_exception,
    NOT coalesce(b.service_days BETWEEN 20 AND 45, false)                              AS flag_unusual_service_days,
    (b.service_start IS NULL OR b.service_end IS NULL)                                 AS flag_missing_service_dates,
    contains(coalesce(b.meter_number, ''), '%')                                        AS flag_split_meter
FROM int_bills_deduplicated b
CROSS JOIN int_rate_bounds r;
