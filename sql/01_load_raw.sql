-- 01_load_raw.sql
-- Land the source CSV unchanged (all text) and assign record_id = 1-based file position.
-- The runner sets `threads = 1` for this step so row_number() follows file order;
-- test T09 in 07_validation_tests.sql verifies record_id alignment with the Python pipeline.

CREATE OR REPLACE TABLE raw_bills AS
SELECT
    row_number() OVER () AS record_id,
    *
FROM read_csv(getvariable('raw_csv'), all_varchar = true, header = true);
