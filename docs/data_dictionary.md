# Data dictionary

## Source

- **Dataset:** NYC Open Data — *Electric Consumption and Cost*, published by NYCHA
- **Portal page:** https://data.cityofnewyork.us/Housing-Development/Electric-Consumption-And-Cost-2010-Sep-2025-/jr24-e7cr
- **CSV export:** https://data.cityofnewyork.us/api/views/jr24-e7cr/rows.csv?accessType=DOWNLOAD
- **File profiled:** 445,111 rows; revenue months 2010-01 to 2023-01
- **Download date:** see `data/raw/SOURCE.md`

Descriptions are the analyst's working interpretation. Confirm them against the
"Columns in this Dataset" panel on the portal page. NYCHA documents `TDS #` as the unique
development identifier and notes that some meters and accounts span multiple developments.

## Source fields (profiled on the file above)

| Project name | Source header | Type | Non-null | Distinct | Example | Description |
|---|---|---|---|---|---|---|
| `development_name` | Development Name | text | 100.0% | 354 | `MOTT HAVEN` | NYCHA development (housing complex) name |
| `borough` | Borough | text | 100.0% | 5 | `BRONX` | NYC borough |
| `account_name` | Account Name | text | 100.0% | 344 | `MOTT HAVEN` | Utility account name (usually the development) |
| `location` | Location | text | 97.4% | 501 | `BLD 04` | Building / location within the development |
| `meter_amr` | Meter AMR | text | 99.9% | 7 | `NONE` | Automated meter reading type |
| `meter_scope` | Meter Scope | text | 5.2% | 105 | `Community Center` | What the meter serves (e.g. building, community centre); mostly blank |
| `tds` | TDS # | integer | 100.0% | 338 | `121` | TDS number: NYCHA's unique development identifier — the development key in this project |
| `edp` | EDP | text | 100.0% | 331 | `244` | NYCHA internal development code |
| `rc_code` | RC Code | text | 100.0% | 374 | `B012100` | Responsibility-centre code |
| `funding_source` | Funding Source | text | 100.0% | 6 | `FEDERAL` | Funding program (e.g. Federal, Mixed finance) |
| `amp` | AMP # | text | 100.0% | 158 | `NY005001210P` | Asset Management Project number |
| `vendor_name` | Vendor Name | text | 100.0% | 4 | `NEW YORK POWER AUTHORITY` | Utility vendor issuing the bill |
| `umis_bill_id` | UMIS BILL ID | integer | 100.0% | 136,018 | `12243029` | Bill identifier; one bill can cover several meters. Higher IDs are issued later |
| `revenue_month` | Revenue Month | date | 100.0% | 133 | `2023-01-01` | Accounting month the bill is booked to — the reporting period used here |
| `service_start` | Service Start Date | date | 100.0% | 756 | `2022-12-23` | Start of the metered service period |
| `service_end` | Service End Date | date | 100.0% | 817 | `2023-01-25` | End of the metered service period |
| `service_days` | # days | decimal | 100.0% | 57 | `33.0` | Days in the service period |
| `meter_number` | Meter Number | text | 100.0% | 8,385 | `4237196` | Meter identifier; a `%` suffix marks a meter split across developments |
| `estimated` | Estimated | text | 100.0% | 3 | `N` | Y if the read was estimated |
| `current_charges` | Current Charges | decimal | 100.0% | 303,101 | `17406.19` | Total charge on the line (= kWh + kW + other charges) |
| `rate_class` | Rate Class | text | 100.0% | 17 | `GOV/NYC/068` | Utility rate class |
| `bill_analyzed` | Bill Analyzed | text | 100.0% | 2 | `Yes` | Bill-review status (Yes / Exception) |
| `kwh` | Consumption (KWH) | decimal | 100.0% | 7,419 | `114400.0` | Energy consumed (kWh) |
| `kwh_charges` | KWH Charges | decimal | 100.0% | 117,067 | `5978.54` | Energy (kWh) charges, $ |
| `kw` | Consumption (KW) | decimal | 100.0% | 12,213 | `200.0` | Billed demand (kW) |
| `kw_charges` | KW Charges | decimal | 100.0% | 112,523 | `2200.0` | Demand (kW) charges, $ |
| `other_charges` | Other Charges | decimal | 100.0% | 281,132 | `9227.65` | All other charges and adjustments, $ |

## Derived fields

| Field | Definition |
|---|---|
| `record_id` | 1-based line position in the source file. Links every output back to the raw record |
| `mwh` | kWh ÷ 1,000 |
| `effective_cost_per_kwh` | Σ cost ÷ Σ kWh at the reported level (never an average of ratios). Includes demand and other charges, so it is **not a tariff rate** |
| `credits` | Sum of negative line charges (credits / adjustments) |
| `row_rate` | Line-level cost ÷ kWh, only where both are > 0; used for extreme-rate flags |
| `typical_meters` | Median meters reporting per development-month |
| `consumption_effect` | (Q₁ − Q₀) × R₀, same month vs prior year |
| `rate_effect` | Q₁ × (R₁ − R₀); labelled "effective-cost effect" in reports |
| `non_comparable_change` | Cost change where either month has no kWh (missing month or zero kWh) |
| `WAPE` | Σ\|actual − forecast\| ÷ Σ actual |

## Processed tables (`data/processed/`)

| Table | Contents |
|---|---|
| `fact_development_month` | Development (TDS) × revenue month, complete panel. kWh, MWh, cost, bill components, credits, record/meter counts, quality-flag counts, `effective_cost_per_kwh`, `is_missing_month`, `flag_meter_count_change`, `top_record_id` (largest source record, for traceability). |
| `dim_development` | One row per development: name, borough, primary vendor, funding source, first/last reported month, typical meter count. |
| `dim_date` | Monthly calendar incl. forecast year, with `prior_year_month` for YoY measures. |
| `portfolio_monthly` | Portfolio totals per month with YoY and reporting coverage. |
| `annual_summary` | Portfolio totals per year: kWh, cost, bill components, effective cost, YoY. |
| `development_year` | Development × year: kWh, cost, effective cost, YoY, share of portfolio cost, rank. |
| `cost_decomposition` | Development × month YoY decomposition: prior/current kWh and cost, `consumption_effect`, `rate_effect` (effective-cost effect), `non_comparable_change`. |
| `cost_bridge` | Portfolio waterfall steps per year (prior cost → effects → current cost). |
| `bill_component_change` | Latest year vs prior year change by bill component. |
| `investigation_table` | Development-months needing investigation: issue, financial magnitude, evidence, possible explanation, `is_primary` (use to avoid double counting). |
| `exclusion_log` | Every excluded source record with reason (`exact_duplicate`, `superseded_bill`, `near_duplicate_same_bill`). |
| `flagged_records` | Retained source records with credits, extreme cost/kWh, unusual or missing service periods. |
| `continuity` | Per development: months reported, zero-kWh months, meter-count changes up to the training cut-off. |
| `forecast_selection` | Forecast eligibility and selection notes for every development. |
| `forecast_backtest` | Rolling one-step-ahead predictions (baseline, SARIMA, 80% interval) with `scored` flag. |
| `forecast_metrics` | MAE/WAPE per development and method; selected method and reason. |
| `forecast_outlook` | Next-12-month forecast kWh and low/base/high planning spend. |
| `scenario_assumptions` | Effective-cost scenario factors and their historical basis. |
