"""Generate docs/data_dictionary.md: source-field profile + processed-table definitions."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nycha_energy import config, prepare  # noqa: E402

DESC = {
    "development_name": "NYCHA development (housing complex) name",
    "borough": "NYC borough",
    "account_name": "Utility account name (usually the development)",
    "location": "Building / location within the development",
    "meter_amr": "Automated meter reading type",
    "meter_scope": "What the meter serves (e.g. building, community centre); mostly blank",
    "tds": "TDS number: NYCHA's unique development identifier — the development key in this project",
    "edp": "NYCHA internal development code",
    "rc_code": "Responsibility-centre code",
    "funding_source": "Funding program (e.g. Federal, Mixed finance)",
    "amp": "Asset Management Project number",
    "vendor_name": "Utility vendor issuing the bill",
    "umis_bill_id": "Bill identifier; one bill can cover several meters. Higher IDs are issued later",
    "revenue_month": "Accounting month the bill is booked to — the reporting period used here",
    "service_start": "Start of the metered service period",
    "service_end": "End of the metered service period",
    "service_days": "Days in the service period",
    "meter_number": "Meter identifier; a `%` suffix marks a meter split across developments",
    "estimated": "Y if the read was estimated",
    "current_charges": "Total charge on the line (= kWh + kW + other charges)",
    "rate_class": "Utility rate class",
    "bill_analyzed": "Bill-review status (Yes / Exception)",
    "kwh": "Energy consumed (kWh)",
    "kwh_charges": "Energy (kWh) charges, $",
    "kw": "Billed demand (kW)",
    "kw_charges": "Demand (kW) charges, $",
    "other_charges": "All other charges and adjustments, $",
}

PROCESSED = {
    "fact_development_month": "Development (TDS) × revenue month, complete panel. kWh, MWh, cost, bill components, credits, record/meter counts, quality-flag counts, `effective_cost_per_kwh`, `is_missing_month`, `flag_meter_count_change`, `top_record_id` (largest source record, for traceability).",
    "dim_development": "One row per development: name, borough, primary vendor, funding source, first/last reported month, typical meter count.",
    "dim_date": "Monthly calendar incl. forecast year, with `prior_year_month` for YoY measures.",
    "portfolio_monthly": "Portfolio totals per month with YoY and reporting coverage.",
    "annual_summary": "Portfolio totals per year: kWh, cost, bill components, effective cost, YoY.",
    "development_year": "Development × year: kWh, cost, effective cost, YoY, share of portfolio cost, rank.",
    "cost_decomposition": "Development × month YoY decomposition: prior/current kWh and cost, `consumption_effect`, `rate_effect` (effective-cost effect), `non_comparable_change`.",
    "cost_bridge": "Portfolio waterfall steps per year (prior cost → effects → current cost).",
    "bill_component_change": "Latest year vs prior year change by bill component.",
    "investigation_table": "Development-months needing investigation: issue, financial magnitude, evidence, possible explanation, `is_primary` (use to avoid double counting).",
    "exclusion_log": "Every excluded source record with reason (`exact_duplicate`, `superseded_bill`, `near_duplicate_same_bill`).",
    "flagged_records": "Retained source records with credits, extreme cost/kWh, unusual or missing service periods.",
    "continuity": "Per development: months reported, zero-kWh months, meter-count changes up to the training cut-off.",
    "forecast_selection": "Forecast eligibility and selection notes for every development.",
    "forecast_backtest": "Rolling one-step-ahead predictions (baseline, SARIMA, 80% interval) with `scored` flag.",
    "forecast_metrics": "MAE/WAPE per development and method; selected method and reason.",
    "forecast_outlook": "Next-12-month forecast kWh and low/base/high planning spend.",
    "scenario_assumptions": "Effective-cost scenario factors and their historical basis.",
}


def main():
    raw = prepare.load_raw()
    std = prepare.standardise(raw)
    inv = {v: k for k, v in prepare.COLUMN_MAP.items()}
    rows = []
    for c in prepare.COLUMN_MAP.values():
        s = std[c]
        ex = s.dropna()
        example = ex.iloc[0] if len(ex) else ""
        if isinstance(example, pd.Timestamp):
            example = example.strftime("%Y-%m-%d")
        rows.append(f"| `{raw.columns[raw.columns.get_loc(c)] if c in raw.columns else c}` | "
                    f"{_orig(inv[c])} | {_type(s)} | "
                    f"{s.notna().mean():.1%} | {s.nunique():,} | `{str(example)[:28]}` | {DESC[c]} |")
    meta = f"{len(raw):,} rows; revenue months {std.revenue_month.min():%Y-%m} to {std.revenue_month.max():%Y-%m}"
    out = f"""# Data dictionary

## Source

- **Dataset:** NYC Open Data — *Electric Consumption and Cost*, published by NYCHA
- **Portal page:** {config.SOURCE_URL}
- **CSV export:** {config.SOURCE_CSV_URL}
- **File profiled:** {meta}
- **Download date:** see `data/raw/SOURCE.md`

Descriptions are the analyst's working interpretation. Confirm them against the
"Columns in this Dataset" panel on the portal page. NYCHA documents `TDS #` as the unique
development identifier and notes that some meters and accounts span multiple developments.

## Source fields (profiled on the file above)

| Project name | Source header | Type | Non-null | Distinct | Example | Description |
|---|---|---|---|---|---|---|
""" + "\n".join(rows) + """

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
| `WAPE` | Σ\\|actual − forecast\\| ÷ Σ actual |

## Processed tables (`data/processed/`)

| Table | Contents |
|---|---|
""" + "\n".join(f"| `{k}` | {v} |" for k, v in PROCESSED.items()) + "\n"
    (ROOT / "docs" / "data_dictionary.md").write_text(out)
    print("docs/data_dictionary.md written")


def _type(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return "date"
    if pd.api.types.is_integer_dtype(s):
        return "integer"
    if pd.api.types.is_float_dtype(s):
        return "decimal"
    return "text"


def _orig(key):
    return {"tds #": "TDS #", "amp #": "AMP #", "# days": "# days", "umis bill id": "UMIS BILL ID",
            "consumption (kwh)": "Consumption (KWH)", "consumption (kw)": "Consumption (KW)",
            "kwh charges": "KWH Charges", "kw charges": "KW Charges", "rc code": "RC Code",
            "meter amr": "Meter AMR", "edp": "EDP"}.get(key, key.title())


if __name__ == "__main__":
    main()
