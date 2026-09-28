"""Energy and financial metrics, year-over-year cost decomposition and anomaly screening.

All ratios are computed from aggregated dollars and aggregated kWh (never by
averaging row-level ratios). "Effective cost per kWh" is total reported charges
divided by total kWh: it bundles energy, demand and other bill components and
adjustments, so it is *not* a tariff rate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _safe_div(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b != 0, a / b, np.nan)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def portfolio_monthly(dm: pd.DataFrame) -> pd.DataFrame:
    m = dm.groupby("revenue_month").agg(
        kwh=("kwh", "sum"), cost=("cost", "sum"),
        kwh_charges=("kwh_charges", "sum"), kw_charges=("kw_charges", "sum"),
        other_charges=("other_charges", "sum"),
        developments_reporting=("is_missing_month", lambda s: (~s).sum()),
        meters_reporting=("n_meters", "sum"),
    ).reset_index()
    m["mwh"] = m["kwh"] / 1_000
    m["effective_cost_per_kwh"] = _safe_div(m["cost"], m["kwh"])
    m["kwh_yoy"] = _safe_div(m["kwh"], m["kwh"].shift(12)) - 1
    m["cost_yoy"] = _safe_div(m["cost"], m["cost"].shift(12)) - 1
    return m


def annual_summary(dm: pd.DataFrame) -> pd.DataFrame:
    a = dm.groupby("year").agg(
        kwh=("kwh", "sum"), cost=("cost", "sum"),
        kwh_charges=("kwh_charges", "sum"), kw_charges=("kw_charges", "sum"),
        other_charges=("other_charges", "sum"), credits=("credits", "sum"),
        developments=("is_missing_month", lambda s: s.groupby(dm.loc[s.index, "tds"]).apply(lambda x: (~x).any()).sum()),
        missing_dev_months=("is_missing_month", "sum"),
    ).reset_index()
    a["mwh"] = a["kwh"] / 1_000
    a["effective_cost_per_kwh"] = _safe_div(a["cost"], a["kwh"])
    a["kwh_yoy"] = _safe_div(a["kwh"], a["kwh"].shift(1)) - 1
    a["cost_yoy"] = _safe_div(a["cost"], a["cost"].shift(1)) - 1
    a["rate_yoy"] = _safe_div(a["effective_cost_per_kwh"], a["effective_cost_per_kwh"].shift(1)) - 1
    return a


def development_year(dm: pd.DataFrame) -> pd.DataFrame:
    d = dm.groupby(["tds", "development_name", "borough", "year"]).agg(
        kwh=("kwh", "sum"), cost=("cost", "sum"),
        months_reported=("is_missing_month", lambda s: (~s).sum()),
    ).reset_index().sort_values(["tds", "year"])
    d["mwh"] = d["kwh"] / 1_000
    d["effective_cost_per_kwh"] = _safe_div(d["cost"], d["kwh"])
    g = d.groupby("tds")
    prev_year = g["year"].shift(1)
    consecutive = prev_year == d["year"] - 1
    d["kwh_yoy"] = np.where(consecutive, _safe_div(d["kwh"], g["kwh"].shift(1)) - 1, np.nan)
    d["cost_yoy"] = np.where(consecutive, _safe_div(d["cost"], g["cost"].shift(1)) - 1, np.nan)
    d["share_of_portfolio_cost"] = d["cost"] / d.groupby("year")["cost"].transform("sum")
    d["cost_rank_in_year"] = d.groupby("year")["cost"].rank(ascending=False, method="first").astype(int)
    return d


# --------------------------------------------------------------------------- #
# Year-over-year cost decomposition
# --------------------------------------------------------------------------- #
def yoy_decomposition(dm: pd.DataFrame, current_year: int) -> pd.DataFrame:
    """Development-month decomposition of the cost change vs the same month a year earlier.

    consumption_effect = (Q1 - Q0) * R0
    rate_effect        = Q1 * (R1 - R0)
    These sum exactly to C1 - C0 when both periods have positive kWh. Pairs where
    a ratio is undefined (missing month, zero kWh) are reported in
    ``non_comparable_change`` so the portfolio bridge still closes.
    """
    cols = ["tds", "development_name", "borough", "month", "kwh", "cost", "is_missing_month"]
    cur = dm.loc[dm["year"] == current_year, cols]
    pri = dm.loc[dm["year"] == current_year - 1, ["tds", "month", "kwh", "cost", "is_missing_month"]]
    x = cur.merge(pri, on=["tds", "month"], suffixes=("_cur", "_pri"), how="outer")
    for c in ("kwh_cur", "cost_cur", "kwh_pri", "cost_pri"):
        x[c] = x[c].fillna(0.0)
    x["comparable"] = (x["kwh_cur"] > 0) & (x["kwh_pri"] > 0)
    r0 = _safe_div(x["cost_pri"], x["kwh_pri"])
    r1 = _safe_div(x["cost_cur"], x["kwh_cur"])
    x["rate_pri"], x["rate_cur"] = r0, r1
    x["cost_change"] = x["cost_cur"] - x["cost_pri"]
    x["consumption_effect"] = np.where(x["comparable"], (x["kwh_cur"] - x["kwh_pri"]) * r0, 0.0)
    x["rate_effect"] = np.where(x["comparable"], x["kwh_cur"] * (r1 - r0), 0.0)
    x["non_comparable_change"] = np.where(x["comparable"], 0.0, x["cost_change"])
    x["year"] = current_year
    x["revenue_month"] = pd.to_datetime(dict(year=current_year, month=x["month"], day=1))
    return x


def bridge(decomp: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Aggregate a decomposition into a waterfall bridge (optionally per group)."""
    keys = [by] if by else []
    g = decomp.groupby(keys) if keys else decomp.assign(_all=1).groupby("_all")
    b = g.agg(prior_cost=("cost_pri", "sum"), consumption_effect=("consumption_effect", "sum"),
              rate_effect=("rate_effect", "sum"), non_comparable_change=("non_comparable_change", "sum"),
              current_cost=("cost_cur", "sum")).reset_index()
    b["check"] = b["prior_cost"] + b["consumption_effect"] + b["rate_effect"] + b["non_comparable_change"] - b["current_cost"]
    assert np.allclose(b["check"], 0, atol=1e-3), "Bridge does not reconcile"
    return b.drop(columns=["check", "_all"], errors="ignore")


def waterfall_table(decomp: pd.DataFrame, current_year: int) -> pd.DataFrame:
    b = bridge(decomp).iloc[0]
    steps = [
        (f"{current_year - 1} cost", b.prior_cost, "total"),
        ("Consumption effect", b.consumption_effect, "delta"),
        ("Effective-cost effect", b.rate_effect, "delta"),
        ("Non-comparable (gaps / zero kWh)", b.non_comparable_change, "delta"),
        (f"{current_year} cost", b.current_cost, "total"),
    ]
    return pd.DataFrame(steps, columns=["step", "amount", "kind"]).assign(sort_order=range(1, 6))


def component_change(dm: pd.DataFrame, current_year: int) -> pd.DataFrame:
    """Change in each reported bill component (kWh, kW demand, other) between years."""
    a = dm.loc[dm["year"].isin([current_year - 1, current_year])].groupby("year")[
        ["kwh_charges", "kw_charges", "other_charges", "cost", "kwh", "kw"]].sum().T
    a.columns = ["prior", "current"]
    a["change"] = a["current"] - a["prior"]
    a["pct_change"] = _safe_div(a["current"], a["prior"]) - 1
    return a.reset_index(names="component")


# --------------------------------------------------------------------------- #
# Anomaly screening
# --------------------------------------------------------------------------- #
def _modified_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(np.nan, index=x.index)
    return 0.6745 * (x - med) / mad


def investigation_table(dm: pd.DataFrame, pm: pd.DataFrame, years: list[int] | None = None) -> pd.DataFrame:
    """Rank development-months that need a closer look. Cause is never asserted."""
    d = dm.sort_values(["tds", "revenue_month"]).copy()
    g = d.groupby("tds")
    d["kwh_ly"], d["cost_ly"], d["missing_ly"] = g["kwh"].shift(12), g["cost"].shift(12), g["is_missing_month"].shift(12)
    d["rate_ly"] = _safe_div(d["cost_ly"], d["kwh_ly"])
    d["kwh_yoy"] = _safe_div(d["kwh"], d["kwh_ly"]) - 1
    d["cost_yoy"] = _safe_div(d["cost"], d["cost_ly"]) - 1

    # 1) Consumption change unusual relative to the development's own YoY history.
    d["log_kwh_yoy"] = np.log(_safe_div(d["kwh"], d["kwh_ly"]).clip(min=1e-9))
    d.loc[~((d["kwh"] > 0) & (d["kwh_ly"] > 0)), "log_kwh_yoy"] = np.nan
    d["z_kwh_yoy"] = d.groupby("tds")["log_kwh_yoy"].transform(_modified_z)

    # 2) Effective cost unusual relative to the portfolio that month and to the development's own norm.
    d = d.merge(pm[["revenue_month", "effective_cost_per_kwh"]].rename(columns={"effective_cost_per_kwh": "portfolio_rate"}),
                on="revenue_month", how="left")
    d["relative_rate"] = d["effective_cost_per_kwh"] / d["portfolio_rate"]
    d["log_rel_rate"] = np.log(d["relative_rate"].where(d["relative_rate"] > 0))
    d["z_rel_rate"] = d.groupby("tds")["log_rel_rate"].transform(_modified_z)
    d["expected_rate"] = d.groupby("tds")["relative_rate"].transform("median") * d["portfolio_rate"]

    rows = []

    def add(mask, issue, magnitude, evidence, explanation):
        sub = d.loc[mask].copy()
        if sub.empty:
            return
        sub["issue"] = issue
        sub["financial_magnitude"] = magnitude(sub)
        sub["evidence"] = sub.apply(evidence, axis=1)
        sub["possible_explanation"] = explanation
        rows.append(sub)

    z = config.ROBUST_Z_THRESHOLD
    add((d["z_kwh_yoy"].abs() > z) & ((d["kwh"] - d["kwh_ly"]).abs() * d["rate_ly"] >= config.MATERIAL_COST_CHANGE / 2),
        "Unusual consumption change vs same month last year",
        lambda s: (s["kwh"] - s["kwh_ly"]) * s["rate_ly"],
        lambda r: (f"kWh {r.kwh_ly:,.0f} -> {r.kwh:,.0f} ({r.kwh_yoy:+.0%}); robust z = {r.z_kwh_yoy:+.1f} "
                   f"vs this development's YoY history; meters {r.n_meters} (typical {r.typical_meters:.0f}); "
                   f"largest record #{r.top_record_id}"),
        "Requires investigation: possible metering/billing-period shift, occupancy or equipment change, "
        "or a catch-up bill. High consumption alone does not prove inefficiency.")

    add((d["z_rel_rate"].abs() > z) & ((d["effective_cost_per_kwh"] - d["expected_rate"]).abs() * d["kwh"] >= config.MATERIAL_COST_CHANGE / 2),
        "Unusual effective cost per kWh",
        lambda s: (s["effective_cost_per_kwh"] - s["expected_rate"]) * s["kwh"],
        lambda r: (f"${r.effective_cost_per_kwh:.3f}/kWh vs expected ${r.expected_rate:.3f} "
                   f"(portfolio ${r.portfolio_rate:.3f}); credits ${r.credits:,.0f}; "
                   f"demand-only rows {r.n_demand_only}; robust z = {r.z_rel_rate:+.1f}; "
                   f"largest record #{r.top_record_id} (${r.top_record_cost:,.0f})"),
        "Requires investigation: credit/adjustment, demand-charge change, estimated read or re-bill. "
        "Effective cost is not a tariff rate.")

    add(d["is_missing_month"] & (d["missing_ly"] == False),  # noqa: E712
        "Missing month (reported in same month last year)",
        lambda s: -s["cost_ly"],
        lambda r: f"No records this month; same month last year cost ${r.cost_ly:,.0f}",
        "Requires investigation: late or missing bill, account transfer, or reporting lag in the release.")

    add(d["flag_meter_count_change"] & d["kwh_ly"].notna(),
        "Change in number of reporting meters",
        lambda s: s["cost"] - s["cost_ly"],
        lambda r: f"{r.n_meters} meters vs typical {r.typical_meters:.0f}; cost ${r.cost_ly:,.0f} -> ${r.cost:,.0f}",
        "Requires investigation: meters added/removed, partial billing, or data-release timing.")

    add((d["cost"] - d["cost_ly"] >= config.MATERIAL_COST_CHANGE) & (d["kwh_yoy"] <= config.STABLE_KWH_BAND)
        & (d["kwh_ly"] > 0),
        "Spending up despite stable or falling consumption",
        lambda s: s["cost"] - s["cost_ly"],
        lambda r: (f"Cost ${r.cost_ly:,.0f} -> ${r.cost:,.0f} ({r.cost_yoy:+.0%}) while kWh {r.kwh_yoy:+.0%}; "
                   f"kW charges ${r.kw_charges:,.0f}; other charges ${r.other_charges:,.0f}"),
        "Requires investigation: higher effective cost (supply price, demand charges, other charges) "
        "or a billing adjustment. Decomposition identifies the arithmetic driver, not the cause.")

    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    if years:
        out = out.loc[out["year"].isin(years)]
    out["abs_magnitude"] = out["financial_magnitude"].abs()
    out = out.sort_values("abs_magnitude", ascending=False)
    # A development-month can trigger several checks; mark the largest one as primary
    # so magnitudes are not double-counted when summed.
    out["is_primary"] = ~out.duplicated(["tds", "revenue_month"])
    out["issues_this_month"] = out.groupby(["tds", "revenue_month"])["issue"].transform("size")
    keep = ["tds", "development_name", "borough", "revenue_month", "issue", "financial_magnitude",
            "evidence", "possible_explanation", "is_primary", "issues_this_month",
            "kwh", "cost", "effective_cost_per_kwh", "n_meters", "top_record_id"]
    out = out[keep].reset_index(drop=True)
    out.insert(0, "investigation_id", [f"INV-{i:04d}" for i in range(1, len(out) + 1)])
    return out
