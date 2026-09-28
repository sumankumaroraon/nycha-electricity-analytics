"""End-to-end pipeline: raw CSV -> clean tables, analysis outputs, figures and reports.

Run from the repository root:

    python -m nycha_energy.pipeline          (with ``src`` on PYTHONPATH, or after ``pip install -e .``)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import analysis, config, forecast, prepare, viz

FLAG_LABELS = {
    "flag_zero_kwh_positive_cost": "Zero kWh with positive cost",
    "flag_demand_only": "…of which demand-only (kW > 0)",
    "flag_zero_kwh_zero_cost": "Zero kWh and zero cost",
    "flag_negative_cost": "Negative cost (credit / adjustment)",
    "flag_negative_kwh": "Negative kWh",
    "flag_extreme_rate_high": "Extreme cost per kWh (high)",
    "flag_extreme_rate_low": "Extreme cost per kWh (low)",
    "flag_estimated": "Estimated read",
    "flag_bill_exception": "Bill analysed = Exception",
    "flag_unusual_service_days": "Unusual service-period length",
    "flag_missing_service_dates": "Missing service dates",
    "flag_missing_kwh": "Missing kWh",
    "flag_missing_cost": "Missing cost",
    "flag_split_meter": "Split meter (allocated %)",
}
FLAG_TREATMENT = {
    "flag_zero_kwh_positive_cost": "Retained. Mostly demand-charge lines billed separately from energy.",
    "flag_demand_only": "Retained. Legitimate demand (kW) billing; excluded from row-level rate checks.",
    "flag_zero_kwh_zero_cost": "Retained; contributes nothing to totals.",
    "flag_negative_cost": "Retained. Treated as credits/adjustments; surfaced in `credits`.",
    "flag_negative_kwh": "Retained if present; none observed.",
    "flag_extreme_rate_high": "Retained; screened in the investigation table.",
    "flag_extreme_rate_low": "Retained; screened in the investigation table.",
    "flag_estimated": "Retained; counted per development-month (`n_estimated`).",
    "flag_bill_exception": "Retained; counted per development-month.",
    "flag_unusual_service_days": "Retained; revenue month used as the reporting period.",
    "flag_missing_service_dates": "Retained; cannot participate in re-issue matching on dates.",
    "flag_missing_kwh": "Retained if present; none observed.",
    "flag_missing_cost": "Retained if present; none observed.",
    "flag_split_meter": "Retained. Amounts appear pre-allocated to the development.",
}


def _md5(path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt_money(x):
    return f"${x:,.0f}" if pd.notna(x) else "–"


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in r.values) + " |")
    return "\n".join(lines)


def build_quality_report(prep: prepare.PreparedData, dm: pd.DataFrame, pm: pd.DataFrame, meta: dict) -> str:
    c, r, ex = prep.counts, prep.records, prep.exclusions
    ex_sum = ex.groupby("reason").agg(records=("record_id", "size"), kwh=("kwh", "sum"),
                                      cost=("current_charges", "sum")).reset_index()
    ex_sum["records"] = ex_sum["records"].map(lambda v: f"{v:,}")
    ex_sum["kwh"] = ex_sum["kwh"].map(lambda v: f"{v:,.0f}")
    ex_sum["cost"] = ex_sum["cost"].map(_fmt_money)

    flag_rows = []
    for f, label in FLAG_LABELS.items():
        m = r[f]
        flag_rows.append(dict(check=label, records=f"{int(m.sum()):,}", share=f"{m.mean():.2%}",
                              cost=_fmt_money(r.loc[m, "current_charges"].sum()), treatment=FLAG_TREATMENT[f]))
    flags = pd.DataFrame(flag_rows)

    cont = prepare.continuity(dm, prep.end_year - 1)
    by_year = dm.groupby("year").agg(
        developments_reporting=("tds", lambda s: dm.loc[s.index].loc[~dm.loc[s.index, "is_missing_month"], "tds"].nunique()),
        missing_dev_months=("is_missing_month", "sum"),
        meter_count_changes=("flag_meter_count_change", "sum")).reset_index()

    med = pm["meters_reporting"].median()
    incomplete = pm.loc[pm["meters_reporting"] < med * (1 - config.METER_COUNT_TOLERANCE),
                        ["revenue_month", "meters_reporting", "developments_reporting"]].copy()
    incomplete["revenue_month"] = incomplete["revenue_month"].dt.strftime("%Y-%m")
    incomplete["vs_median_meters"] = (incomplete["meters_reporting"] / med - 1).map(lambda v: f"{v:+.0%}")

    top_rate = (r.loc[r["row_rate"].notna()].nlargest(10, "row_rate")
                [["record_id", "development_name", "revenue_month", "meter_number", "kwh", "current_charges", "row_rate"]])
    top_rate["revenue_month"] = top_rate["revenue_month"].dt.strftime("%Y-%m")
    top_rate["kwh"] = top_rate["kwh"].map(lambda v: f"{v:,.0f}")
    top_rate["current_charges"] = top_rate["current_charges"].map(lambda v: f"${v:,.2f}")
    top_rate["row_rate"] = top_rate["row_rate"].map(lambda v: f"${v:,.3f}")

    kept_cost = r["current_charges"].sum()
    kept_kwh = r["kwh"].sum()
    lo, hi = prep.rate_bounds
    return f"""# Data-quality report

_Generated automatically by `nycha_energy.pipeline` on {meta['run_utc']}. Do not edit by hand._

## Source

| Item | Value |
|---|---|
| Dataset | NYC Open Data — Electric Consumption and Cost (`jr24-e7cr`) |
| File | `{meta['raw_file']}` |
| MD5 | `{meta['raw_md5']}` |
| Rows in file | {c['raw_rows']:,} |
| Revenue months in file | {c['raw_min_month']:%Y-%m} to {c['raw_max_month']:%Y-%m} |
| Analysis window | {prep.start_year}-01 to {prep.end_year}-12 (last complete calendar year = {prep.end_year}) |

## What one row represents

Each row is one **meter line on a utility bill for one revenue month**. A bill (`UMIS BILL ID`)
can cover several meters, and a development (`TDS #`) has many meters, so repeated
development-month rows are expected and are **not** duplicates. `Current Charges` equals
`KWH Charges + KW Charges + Other charges` on every row (verified), so bill components
reconcile to the total.

## Row flow

| Step | Rows |
|---|---|
| Rows in file | {c['raw_rows']:,} |
| Outside analysis window (not an exclusion) | {c['outside_window_rows']:,} |
| In analysis window | {c['window_rows']:,} |
| Excluded — exact duplicates | {c['exact_duplicates']:,} |
| Excluded — superseded bill versions | {c['superseded_bills']:,} |
| Excluded — same-bill near duplicates | {c['near_duplicates_same_bill']:,} |
| **Retained for analysis** | **{c['retained_rows']:,}** |

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

{_md_table(ex_sum)}

**Sensitivity.** If re-issued bills were summed instead of replaced, window totals would be
{_fmt_money(c['cost_if_reissues_summed'])} and {c['kwh_if_reissues_summed']:,.0f} kWh, versus
{_fmt_money(kept_cost)} and {kept_kwh:,.0f} kWh retained
({c['cost_if_reissues_summed'] / kept_cost - 1:+.1%} cost). The choice matters and should be
confirmed with the data owner.

## Flags (retained records)

Row-level effective cost bounds (0.5th / 99.5th percentile of rows with kWh > 0 and cost > 0):
**${lo:.3f} – ${hi:.3f} per kWh**.

{_md_table(flags)}

## Development coverage

- Developments (TDS #) in window: **{dm['tds'].nunique()}**
- Continuous monthly history through {prep.end_year - 1}: **{int(cont['is_continuous'].sum())}**

{_md_table(by_year)}

### Months with incomplete reporting

Months where the number of reporting meters is more than {config.METER_COUNT_TOLERANCE:.0%} below the
median month ({med:,.0f} meters). Totals for these months are understated by missing bills,
not necessarily by lower demand.

{_md_table(incomplete) if len(incomplete) else "_None._"}

## Highest row-level effective costs

{_md_table(top_rate)}
"""


def _single_record_note(records: pd.DataFrame, dy: pd.DataFrame, year: int, share: float = 0.25) -> str:
    """If a top-15 development's annual total is dominated by one record, say so on the chart."""
    top = dy.loc[dy["year"] == year].nlargest(15, "cost")
    r = records.loc[(records["revenue_month"].dt.year == year) & records["tds"].isin(top["tds"])]
    big = r.loc[r.groupby("tds")["current_charges"].idxmax()].merge(top[["tds", "cost"]], on="tds")
    big = big.loc[big["current_charges"] > share * big["cost"]]
    return "; ".join(f"{viz.nice_name(b.development_name)} includes a single record of ${b.current_charges:,.0f} "
                     f"(record #{b.record_id}, {b.revenue_month:%b %Y}) — see investigation table"
                     for b in big.itertuples())


def build_dimensions(dm: pd.DataFrame, prep: prepare.PreparedData):
    r = prep.records
    dim_dev = (dm.groupby(["tds", "development_name", "borough", "primary_vendor", "funding_source"], dropna=False)
                 .agg(first_month=("revenue_month", lambda s: s[~dm.loc[s.index, "is_missing_month"]].min()),
                      last_month=("revenue_month", lambda s: s[~dm.loc[s.index, "is_missing_month"]].max()),
                      months_reported=("is_missing_month", lambda s: (~s).sum()),
                      typical_meters=("typical_meters", "first"))
                 .reset_index())
    vendors = r.groupby("tds")["vendor_name"].nunique().rename("n_vendors")
    dim_dev = dim_dev.merge(vendors, on="tds", how="left")
    months = pd.date_range(dm["revenue_month"].min(), dm["revenue_month"].max() + pd.DateOffset(years=1), freq="MS")
    dim_date = pd.DataFrame({"revenue_month": months})
    dim_date["year"] = dim_date["revenue_month"].dt.year
    dim_date["month"] = dim_date["revenue_month"].dt.month
    dim_date["month_name"] = dim_date["revenue_month"].dt.strftime("%b")
    dim_date["quarter"] = "Q" + dim_date["revenue_month"].dt.quarter.astype(str)
    dim_date["year_month"] = dim_date["revenue_month"].dt.strftime("%Y-%m")
    dim_date["prior_year_month"] = dim_date["revenue_month"] - pd.DateOffset(years=1)
    dim_date["is_forecast_period"] = dim_date["year"] > prep.end_year
    return dim_dev, dim_date


def run(write: bool = True) -> dict:
    for d in (config.DATA_PROCESSED, config.DATA_INTERIM, config.FIGURES):
        d.mkdir(parents=True, exist_ok=True)

    prep = prepare.prepare()
    dm = prepare.development_month(prep.records, prep.start_year, prep.end_year)
    pm = analysis.portfolio_monthly(dm)
    annual = analysis.annual_summary(dm)
    dy = analysis.development_year(dm)
    y1 = prep.end_year
    decomp = analysis.yoy_decomposition(dm, y1)
    wf = analysis.waterfall_table(decomp, y1)
    comp = analysis.component_change(dm, y1)
    decomp_all = pd.concat([analysis.yoy_decomposition(dm, y) for y in range(prep.start_year + 1, y1 + 1)],
                           ignore_index=True)
    wf_all = pd.concat([analysis.waterfall_table(decomp_all.loc[decomp_all["year"] == y], y).assign(year=y)
                        for y in range(prep.start_year + 1, y1 + 1)], ignore_index=True)
    inv = analysis.investigation_table(dm, pm, years=list(range(prep.start_year + 1, y1 + 1)))
    selection, backtest, fmetrics, outlook = forecast.run(dm, y1 - 1, y1)
    scen, assumptions = forecast.spending_scenarios(outlook, dm, annual, y1)
    dim_dev, dim_date = build_dimensions(dm, prep)

    meta = dict(
        run_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        raw_file=str(config.RAW_CSV.relative_to(config.ROOT)) if config.RAW_CSV.is_relative_to(config.ROOT) else str(config.RAW_CSV),
        raw_md5=_md5(config.RAW_CSV),
        raw_rows=prep.counts["raw_rows"],
        raw_coverage=f"{prep.counts['raw_min_month']:%Y-%m} to {prep.counts['raw_max_month']:%Y-%m}",
        analysis_window=f"{prep.start_year}-01 to {y1}-12",
        train_period=f"{prep.start_year}-01 to {y1 - 1}-12",
        test_period=f"{y1}-01 to {y1}-12",
        retained_rows=prep.counts["retained_rows"],
        developments=int(dm["tds"].nunique()),
    )

    outputs = {
        "fact_development_month": dm, "dim_development": dim_dev, "dim_date": dim_date,
        "portfolio_monthly": pm, "annual_summary": annual, "development_year": dy,
        "cost_decomposition": decomp_all, "cost_bridge": wf_all, "bill_component_change": comp,
        "investigation_table": inv, "exclusion_log": prep.exclusions,
        "forecast_selection": selection, "forecast_backtest": backtest, "forecast_metrics": fmetrics,
        "forecast_outlook": scen, "scenario_assumptions": assumptions,
        "flagged_records": prep.records.loc[
            prep.records[["flag_negative_cost", "flag_extreme_rate_high", "flag_extreme_rate_low",
                          "flag_unusual_service_days", "flag_missing_service_dates"]].any(axis=1)],
        "continuity": prepare.continuity(dm, y1 - 1),
    }
    if write:
        for name, df in outputs.items():
            df.to_csv(config.DATA_PROCESSED / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        prep.records.to_csv(config.DATA_INTERIM / "clean_records.csv.gz", index=False,
                            date_format="%Y-%m-%d", compression="gzip")
        (config.REPORTS / "data_quality_report.md").write_text(build_quality_report(prep, dm, pm, meta))
        (config.REPORTS / "run_metadata.json").write_text(json.dumps(meta, indent=2))

        viz.data_quality(prep.counts, prep.records[list(FLAG_LABELS)].sum().rename(FLAG_LABELS).loc[lambda s: s > 0],
                         config.FIGURES / "01_data_quality.png")
        viz.portfolio_trend(pm, config.FIGURES / "02_portfolio_trend.png")
        viz.bill_components(annual, config.FIGURES / "03_bill_components.png")
        viz.waterfall(wf, config.FIGURES / "04_cost_bridge.png", f"{y1 - 1} → {y1}")
        viz.concentration(dy, y1, config.FIGURES / "05_spend_concentration.png",
                          extra_note=_single_record_note(prep.records, dy, y1))
        viz.forecast_backtest(backtest, fmetrics, dm, config.FIGURES / "06_forecast_backtest.png")

        from . import dashboard  # after all CSVs and run_metadata.json exist
        dashboard.build()

    outputs.update(prep=prep, meta=meta, waterfall=wf)
    return outputs


if __name__ == "__main__":
    out = run()
    m = out["meta"]
    print(f"Done. {m['retained_rows']:,} records retained; window {m['analysis_window']}; "
          "outputs in data/processed/, dashboard in docs/index.html")
