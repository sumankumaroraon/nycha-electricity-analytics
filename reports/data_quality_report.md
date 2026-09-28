# Data-quality report

_Generated automatically by `nycha_energy.pipeline` on 2026-09-28 15:36 UTC. Do not edit by hand._

## Source

| Item | Value |
|---|---|
| Dataset | NYC Open Data — Electric Consumption and Cost (`jr24-e7cr`) |
| File | `data/raw/Electric_Consumption_And_Cost.csv` |
| MD5 | `30f91c320c5c3aef05b280a150b8662d` |
| Rows in file | 445,111 |
| Revenue months in file | 2010-01 to 2023-01 |
| Analysis window | 2019-01 to 2022-12 (last complete calendar year = 2022) |

## What one row represents

Each row is one **meter line on a utility bill for one revenue month**. A bill (`UMIS BILL ID`)
can cover several meters, and a development (`TDS #`) has many meters, so repeated
development-month rows are expected and are **not** duplicates. `Current Charges` equals
`KWH Charges + KW Charges + Other charges` on every row (verified), so bill components
reconcile to the total.

## Row flow

| Step | Rows |
|---|---|
| Rows in file | 445,111 |
| Outside analysis window (not an exclusion) | 263,780 |
| In analysis window | 181,331 |
| Excluded — exact duplicates | 15,773 |
| Excluded — superseded bill versions | 5,888 |
| Excluded — same-bill near duplicates | 519 |
| **Retained for analysis** | **159,151** |

## Exclusions

Only two situations remove a record. Every excluded `record_id` is listed in
`data/processed/exclusion_log.csv` with its reason.

1. **Exact duplicates** — every source field identical to an earlier row. These are
   concentrated in a few revenue months (e.g. January of several years), where the file
   contains a second copy of the month.
2. **Re-issued bills** — the same meter, revenue month and service period appears under more
   than one bill ID with different amounts. The record with the **highest bill ID** is kept
   as the current version (bill IDs increase over time in this file). Rows with the same bill
   ID that differ only in a descriptive field are kept once.

| reason | records | kwh | cost |
|---|---|---|---|
| exact_duplicate | 15,773 | 451,703,455 | $50,722,968 |
| near_duplicate_same_bill | 519 | 5,867,337 | $746,884 |
| superseded_bill | 5,888 | 111,617,779 | $10,622,531 |

**Sensitivity.** If re-issued bills were summed instead of replaced, window totals would be
$652,295,031 and 4,618,336,608 kWh, versus
$640,925,616 and 4,500,851,492 kWh retained
(+1.8% cost). The choice matters and should be
confirmed with the data owner.

## Flags (retained records)

Row-level effective cost bounds (0.5th / 99.5th percentile of rows with kWh > 0 and cost > 0):
**$0.021 – $0.385 per kWh**.

| check | records | share | cost | treatment |
|---|---|---|---|---|
| Zero kWh with positive cost | 57,871 | 36.36% | $92,961,207 | Retained. Mostly demand-charge lines billed separately from energy. |
| …of which demand-only (kW > 0) | 57,726 | 36.27% | $92,809,255 | Retained. Legitimate demand (kW) billing; excluded from row-level rate checks. |
| Zero kWh and zero cost | 1,069 | 0.67% | $0 | Retained; contributes nothing to totals. |
| Negative cost (credit / adjustment) | 215 | 0.14% | $-37,584 | Retained. Treated as credits/adjustments; surfaced in `credits`. |
| Negative kWh | 0 | 0.00% | $0 | Retained if present; none observed. |
| Extreme cost per kWh (high) | 500 | 0.31% | $4,262,328 | Retained; screened in the investigation table. |
| Extreme cost per kWh (low) | 500 | 0.31% | $292,641 | Retained; screened in the investigation table. |
| Estimated read | 53,554 | 33.65% | $190,667,345 | Retained; counted per development-month (`n_estimated`). |
| Bill analysed = Exception | 13,934 | 8.76% | $41,506,546 | Retained; counted per development-month. |
| Unusual service-period length | 232 | 0.15% | $1,296,131 | Retained; revenue month used as the reporting period. |
| Missing service dates | 5 | 0.00% | $36 | Retained; cannot participate in re-issue matching on dates. |
| Missing kWh | 0 | 0.00% | $0 | Retained if present; none observed. |
| Missing cost | 0 | 0.00% | $0 | Retained if present; none observed. |
| Split meter (allocated %) | 488 | 0.31% | $7,218,591 | Retained. Amounts appear pre-allocated to the development. |

## Development coverage

- Developments (TDS #) in window: **335**
- Continuous monthly history through 2021: **328**

| year | developments_reporting | missing_dev_months | meter_count_changes |
|---|---|---|---|
| 2019 | 335 | 42 | 185 |
| 2020 | 334 | 12 | 108 |
| 2021 | 334 | 14 | 111 |
| 2022 | 334 | 88 | 219 |

### Months with incomplete reporting

Months where the number of reporting meters is more than 10% below the
median month (3,369 meters). Totals for these months are understated by missing bills,
not necessarily by lower demand.

| revenue_month | meters_reporting | developments_reporting | vs_median_meters |
|---|---|---|---|
| 2022-12 | 2650 | 316 | -21% |

## Highest row-level effective costs

| record_id | development_name | revenue_month | meter_number | kwh | current_charges | row_rate |
|---|---|---|---|---|---|---|
| 18453 | WEST BRIGHTON II | 2022-07 | 9863107_S017500-12.2% | 69,491 | $3,551,569.45 | $51.108 |
| 178786 | WEST BRIGHTON I | 2019-02 | 7860113_1600-87.8% | 548 | $27,063.29 | $49.386 |
| 132310 | MORRISANIA | 2020-02 | 8096662-58.5 | 222 | $9,215.91 | $41.513 |
| 54708 | REDFERN | 2021-09 | 80659819 | 262 | $8,280.88 | $31.606 |
| 56870 | BEACH 41ST STREET-BEACH CHANNEL DRIVE | 2021-09 | 80340656 | 141 | $3,061.34 | $21.712 |
| 18100 | BUSHWICK II CDA (GROUP E) | 2022-07 | 2816102 | 18 | $348.55 | $19.364 |
| 7167 | BUSHWICK II (GROUPS A & C) | 2022-11 | 9948690 | 27 | $464.78 | $17.214 |
| 7532 | REHAB PROGRAM (TAFT REHABS) | 2022-11 | 13186187 | 80 | $961.55 | $12.019 |
| 20775 | BUSHWICK II (GROUPS A & C) | 2022-07 | 9948690 | 42 | $427.58 | $10.180 |
| 181445 | SHELTON HOUSE | 2019-01 | 3703376 | 3 | $29.22 | $9.740 |
