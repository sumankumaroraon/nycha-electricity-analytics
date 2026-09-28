"""Load, standardise, quality-flag and aggregate the NYCHA electricity records.

Design principles
-----------------
* The raw file is never modified. Every record keeps ``record_id`` (its 1-based
  position in the source file) so any output can be traced back.
* Only two kinds of rows are *excluded*: exact duplicates, and superseded
  re-issues of a bill (same meter, same revenue month, same service period,
  different bill ID). Every exclusion is written to an exclusion log.
* Everything else that looks unusual (credits, demand-only rows, extreme
  cost per kWh, estimated reads, ...) is *flagged and retained*.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

# Source header -> snake_case name. Matching is done on a normalised header so
# small formatting changes between releases (case, spacing, '#') do not break it.
COLUMN_MAP = {
    "development name": "development_name",
    "borough": "borough",
    "account name": "account_name",
    "location": "location",
    "meter amr": "meter_amr",
    "meter scope": "meter_scope",
    "tds #": "tds",
    "edp": "edp",
    "rc code": "rc_code",
    "funding source": "funding_source",
    "amp #": "amp",
    "vendor name": "vendor_name",
    "umis bill id": "umis_bill_id",
    "revenue month": "revenue_month",
    "service start date": "service_start",
    "service end date": "service_end",
    "# days": "service_days",
    "meter number": "meter_number",
    "estimated": "estimated",
    "current charges": "current_charges",
    "rate class": "rate_class",
    "bill analyzed": "bill_analyzed",
    "consumption (kwh)": "kwh",
    "kwh charges": "kwh_charges",
    "consumption (kw)": "kw",
    "kw charges": "kw_charges",
    "other charges": "other_charges",
}
NUMERIC_COLS = ["service_days", "current_charges", "kwh", "kwh_charges", "kw", "kw_charges", "other_charges"]
TEXT_COLS = [
    "development_name", "borough", "account_name", "location", "meter_amr", "meter_scope",
    "rc_code", "funding_source", "amp", "vendor_name", "meter_number", "estimated",
    "rate_class", "bill_analyzed",
]
FLAG_COLS = [
    "flag_zero_kwh_positive_cost", "flag_demand_only", "flag_zero_kwh_zero_cost",
    "flag_negative_cost", "flag_negative_kwh", "flag_extreme_rate_high", "flag_extreme_rate_low",
    "flag_estimated", "flag_bill_exception", "flag_unusual_service_days",
    "flag_missing_service_dates", "flag_missing_kwh", "flag_missing_cost", "flag_split_meter",
]


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())


def load_raw(path=config.RAW_CSV) -> pd.DataFrame:
    """Read the source CSV as text, add ``record_id`` and rename columns."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    rename = {}
    for col in raw.columns:
        key = _norm_header(col)
        if key in COLUMN_MAP:
            rename[col] = COLUMN_MAP[key]
    missing = set(COLUMN_MAP.values()) - set(rename.values())
    if missing:
        raise ValueError(f"Source file is missing expected columns: {sorted(missing)}")
    raw = raw.rename(columns=rename)[list(COLUMN_MAP.values())]
    raw.insert(0, "record_id", np.arange(1, len(raw) + 1))
    return raw


def standardise(raw: pd.DataFrame) -> pd.DataFrame:
    """Type-cast and tidy text, dates and numbers. Does not drop rows."""
    df = raw.copy()
    for c in TEXT_COLS:
        df[c] = df[c].str.strip().str.replace(r"\s+", " ", regex=True)
    df["development_name"] = df["development_name"].str.upper()
    df["borough"] = df["borough"].str.upper()
    df["tds"] = pd.to_numeric(df["tds"], errors="coerce").astype("Int64")
    df["umis_bill_id"] = pd.to_numeric(df["umis_bill_id"], errors="coerce").astype("Int64")
    df["revenue_month"] = pd.to_datetime(df["revenue_month"], format="%Y-%m", errors="coerce")
    for c in ("service_start", "service_end"):
        df[c] = pd.to_datetime(df[c], format="%m/%d/%Y", errors="coerce")
    for c in NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c].str.replace(",", "", regex=False), errors="coerce")
    return df


def detect_end_year(df: pd.DataFrame) -> int:
    """Last calendar year with all 12 revenue months present (or the env override)."""
    if config.END_YEAR_OVERRIDE:
        return int(config.END_YEAR_OVERRIDE)
    months = df["revenue_month"].dropna()
    per_year = months.dt.to_period("M").drop_duplicates().dt.year.value_counts()
    complete = sorted(y for y, n in per_year.items() if n == 12)
    if not complete:
        raise ValueError("No complete calendar year found in the file.")
    return int(complete[-1])


@dataclass
class PreparedData:
    records: pd.DataFrame          # analysis-window records after exclusions, with flags
    exclusions: pd.DataFrame       # one row per excluded record with reason
    start_year: int
    end_year: int
    counts: dict = field(default_factory=dict)
    rate_bounds: tuple = (np.nan, np.nan)


def _deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove exact duplicates and superseded bill re-issues. Returns (kept, excluded)."""
    source_cols = list(COLUMN_MAP.values())
    log_cols = ["record_id", "tds", "development_name", "meter_number", "revenue_month",
                "umis_bill_id", "kwh", "current_charges"]
    exact = df.duplicated(subset=source_cols, keep="first")
    excl_exact = df.loc[exact, log_cols].assign(
        reason="exact_duplicate", detail="All source fields identical to an earlier record")
    df = df.loc[~exact].copy()

    # Same meter, same revenue month, same service period (and development): the
    # record with the highest UMIS bill ID is treated as the current version.
    key = ["tds", "meter_number", "revenue_month", "service_start", "service_end"]
    df = df.sort_values(["umis_bill_id", "record_id"], ascending=[False, True])
    grp = df.groupby(key, dropna=False)
    rank = grp.cumcount()
    max_bill = grp["umis_bill_id"].transform("max")
    n_in_group = grp["record_id"].transform("size")
    drop = rank > 0
    reason = np.where(df["umis_bill_id"] < max_bill, "superseded_bill", "near_duplicate_same_bill")
    excl_rebill = df.loc[drop, log_cols].assign(
        reason=reason[drop.to_numpy()],
        detail="Same meter, revenue month and service period as a record with bill ID "
               + max_bill[drop].astype(str) + f"; kept the highest bill ID")
    kept = df.loc[~drop].copy()
    kept["n_versions_same_period"] = n_in_group[~drop].to_numpy()
    kept = kept.sort_values("record_id").reset_index(drop=True)
    excluded = pd.concat([excl_exact, excl_rebill], ignore_index=True)
    return kept, excluded


def _flag(df: pd.DataFrame) -> tuple[pd.DataFrame, tuple]:
    df = df.copy()
    k, c = df["kwh"], df["current_charges"]
    df["row_rate"] = np.where((k > 0) & (c > 0), c / k.where(k > 0), np.nan)
    lo, hi = df["row_rate"].quantile([config.EXTREME_RATE_LOWER_PCT, config.EXTREME_RATE_UPPER_PCT])
    df["flag_zero_kwh_positive_cost"] = (k == 0) & (c > 0)
    df["flag_demand_only"] = df["flag_zero_kwh_positive_cost"] & (df["kw"] > 0)
    df["flag_zero_kwh_zero_cost"] = (k == 0) & (c == 0)
    df["flag_negative_cost"] = c < 0
    df["flag_negative_kwh"] = k < 0
    df["flag_extreme_rate_high"] = df["row_rate"] > hi
    df["flag_extreme_rate_low"] = df["row_rate"] < lo
    df["flag_estimated"] = df["estimated"].eq("Y")
    df["flag_bill_exception"] = df["bill_analyzed"].eq("Exception")
    df["flag_unusual_service_days"] = ~df["service_days"].between(config.MIN_SERVICE_DAYS, config.MAX_SERVICE_DAYS)
    df["flag_missing_service_dates"] = df["service_start"].isna() | df["service_end"].isna()
    df["flag_missing_kwh"] = k.isna()
    df["flag_missing_cost"] = c.isna()
    df["flag_split_meter"] = df["meter_number"].str.contains("%", regex=False, na=False)
    df["n_flags"] = df[FLAG_COLS].sum(axis=1)
    return df, (float(lo), float(hi))


def prepare(path=config.RAW_CSV) -> PreparedData:
    raw = load_raw(path)
    df = standardise(raw)
    counts = {"raw_rows": len(df), "raw_min_month": df["revenue_month"].min(),
              "raw_max_month": df["revenue_month"].max(),
              "unparseable_revenue_month": int(df["revenue_month"].isna().sum())}
    end_year = detect_end_year(df)
    start = pd.Timestamp(config.START_YEAR, 1, 1)
    end = pd.Timestamp(end_year, 12, 1)
    in_window = df["revenue_month"].between(start, end)
    counts["outside_window_rows"] = int((~in_window).sum())
    df = df.loc[in_window].copy()
    counts["window_rows"] = len(df)

    kept, excluded = _deduplicate(df)
    counts["exact_duplicates"] = int((excluded["reason"] == "exact_duplicate").sum())
    counts["superseded_bills"] = int((excluded["reason"] == "superseded_bill").sum())
    counts["near_duplicates_same_bill"] = int((excluded["reason"] == "near_duplicate_same_bill").sum())
    counts["retained_rows"] = len(kept)
    # Sensitivity: what the totals would be if re-issued bills were summed instead.
    dedup_exact_only = df.drop_duplicates(subset=list(COLUMN_MAP.values()))
    counts["cost_if_reissues_summed"] = float(dedup_exact_only["current_charges"].sum())
    counts["kwh_if_reissues_summed"] = float(dedup_exact_only["kwh"].sum())

    flagged, bounds = _flag(kept)
    return PreparedData(flagged, excluded.sort_values("record_id").reset_index(drop=True),
                        config.START_YEAR, end_year, counts, bounds)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def development_month(records: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    """Aggregate to development (TDS) x revenue month on a complete monthly panel.

    Months where a development has no records are kept as rows with
    ``is_missing_month = True`` so gaps are visible rather than silently dropped.
    """
    r = records
    agg = r.groupby(["tds", "revenue_month"]).agg(
        kwh=("kwh", "sum"),
        cost=("current_charges", "sum"),
        kw=("kw", "sum"),
        kwh_charges=("kwh_charges", "sum"),
        kw_charges=("kw_charges", "sum"),
        other_charges=("other_charges", "sum"),
        credits=("current_charges", lambda s: s[s < 0].sum()),
        n_records=("record_id", "size"),
        n_meters=("meter_number", "nunique"),
        n_estimated=("flag_estimated", "sum"),
        n_negative_cost=("flag_negative_cost", "sum"),
        n_demand_only=("flag_demand_only", "sum"),
        n_zero_kwh_positive_cost=("flag_zero_kwh_positive_cost", "sum"),
        n_extreme_rate=("flag_extreme_rate_high", "sum"),
        n_extreme_rate_low=("flag_extreme_rate_low", "sum"),
        n_bill_exception=("flag_bill_exception", "sum"),
        n_reissued=("n_versions_same_period", lambda s: (s > 1).sum()),
    ).reset_index()
    agg["n_extreme_rate"] += agg.pop("n_extreme_rate_low")
    # Largest single record in each development-month, for traceability.
    top = (r.assign(_abs=r["current_charges"].abs())
             .sort_values("_abs", ascending=False)
             .drop_duplicates(["tds", "revenue_month"])
             [["tds", "revenue_month", "record_id", "current_charges"]]
             .rename(columns={"record_id": "top_record_id", "current_charges": "top_record_cost"}))
    agg = agg.merge(top, on=["tds", "revenue_month"], how="left")

    dims = (r.sort_values("revenue_month")
             .groupby("tds")
             .agg(development_name=("development_name", "last"),
                  borough=("borough", "last"),
                  primary_vendor=("vendor_name", lambda s: s.mode().iat[0]),
                  funding_source=("funding_source", lambda s: s.mode().iat[0]))
             .reset_index())

    months = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    panel = pd.MultiIndex.from_product([dims["tds"], months], names=["tds", "revenue_month"]).to_frame(index=False)
    dm = panel.merge(agg, on=["tds", "revenue_month"], how="left").merge(dims, on="tds", how="left")
    dm["is_missing_month"] = dm["n_records"].isna()
    count_cols = [c for c in dm.columns if c.startswith("n_")]
    dm["top_record_id"] = dm["top_record_id"].astype("Int64")
    dm[count_cols] = dm[count_cols].fillna(0).astype(int)

    dm["mwh"] = dm["kwh"] / 1_000
    dm["effective_cost_per_kwh"] = np.where(dm["kwh"] > 0, dm["cost"] / dm["kwh"].where(dm["kwh"] > 0), np.nan)
    dm["year"] = dm["revenue_month"].dt.year
    dm["month"] = dm["revenue_month"].dt.month

    typical = dm.loc[~dm["is_missing_month"]].groupby("tds")["n_meters"].median().rename("typical_meters")
    dm = dm.merge(typical, on="tds", how="left")
    dm["meter_count_ratio"] = dm["n_meters"] / dm["typical_meters"]
    dm["flag_meter_count_change"] = (~dm["is_missing_month"]) & (
        (dm["meter_count_ratio"] - 1).abs() > config.METER_COUNT_TOLERANCE)
    dm["has_quality_flag"] = (dm[["n_negative_cost", "n_extreme_rate", "n_bill_exception"]].sum(axis=1) > 0) | \
        dm["flag_meter_count_change"] | dm["is_missing_month"]

    lead = ["tds", "development_name", "borough", "revenue_month", "year", "month"]
    return dm[lead + [c for c in dm.columns if c not in lead]].sort_values(["tds", "revenue_month"]).reset_index(drop=True)


def continuity(dm: pd.DataFrame, through_year: int | None = None) -> pd.DataFrame:
    """Per development: months reported, gaps and coverage stability up to ``through_year``."""
    d = dm if through_year is None else dm.loc[dm["year"] <= through_year]
    out = d.groupby(["tds", "development_name", "borough"]).agg(
        months_in_window=("revenue_month", "size"),
        months_reported=("is_missing_month", lambda s: (~s).sum()),
        months_zero_kwh=("kwh", lambda s: (s.fillna(0) <= 0).sum()),
        meter_count_changes=("flag_meter_count_change", "sum"),
        total_kwh=("kwh", "sum"),
        total_cost=("cost", "sum"),
    ).reset_index()
    out["is_continuous"] = out["months_reported"] == out["months_in_window"]
    return out
