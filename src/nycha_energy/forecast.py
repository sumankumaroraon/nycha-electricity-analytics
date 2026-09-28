"""Monthly consumption forecasting: seasonal-naive baseline vs SARIMA.

Protocol
--------
* Developments are ranked using training-period data only. A top-ranked
  development is replaced only if its test-period data is *unavailable*
  (fewer than 6 reported, stable-coverage months); test values are never used.
* SARIMA orders are chosen once per development by AIC on the training data.
* Evaluation is a rolling one-month-ahead forecast over the test year: the
  prediction for month *t* uses only months before *t*. The model is refit at
  every step.
* The approach with the lower WAPE over the test year is kept per development.
"""
from __future__ import annotations

import itertools
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from . import config

MIN_SCORABLE_MONTHS = 6


def select_developments(dm: pd.DataFrame, train_end_year: int, n: int = config.N_FORECAST_DEVELOPMENTS,
                        max_per_borough: int = 2) -> pd.DataFrame:
    """Eligible = every training month reported, positive kWh, and no meter-count changes.

    Among eligible developments pick the largest by training kWh (materiality),
    at most ``max_per_borough`` per borough for coverage across the portfolio.
    """
    t = dm.loc[dm["year"] <= train_end_year]
    # Meter-count stability is judged against the training-period median only.
    typical = t.loc[~t["is_missing_month"]].groupby("tds")["n_meters"].median()
    t = t.assign(_ratio=t["n_meters"] / t["tds"].map(typical))
    s = t.groupby(["tds", "development_name", "borough"]).agg(
        months=("revenue_month", "size"),
        missing=("is_missing_month", "sum"),
        nonpositive_kwh=("kwh", lambda x: (x.fillna(0) <= 0).sum()),
        meter_changes=("_ratio", lambda x: ((x - 1).abs() > config.METER_COUNT_TOLERANCE).sum()),
        train_kwh=("kwh", "sum"),
    ).reset_index()
    s["eligible"] = (s["missing"] == 0) & (s["nonpositive_kwh"] == 0) & (s["meter_changes"] == 0)
    ranked = s.loc[s["eligible"]].sort_values("train_kwh", ascending=False)
    s["candidate_rank"] = s["tds"].map(dict(zip(ranked["tds"], range(1, len(ranked) + 1))))
    s["selected"] = False
    s["selection_note"] = np.where(s["eligible"], "Eligible, not needed", "Not eligible")
    return s


def _pick(selection: pd.DataFrame, dm: pd.DataFrame, test_year: int, n: int, max_per_borough: int = 2):
    """Walk candidates in rank order, respecting the borough cap. A candidate is
    replaced only if its *test-period data is unavailable* (fewer than
    MIN_SCORABLE_MONTHS reported months with stable coverage); test values are
    never used to choose developments."""
    test = dm.loc[dm["year"] == test_year]
    scorable = test.loc[~test["is_missing_month"] & ~test["flag_meter_count_change"] & (test["kwh"] > 0)] \
        .groupby("tds").size()
    chosen, per_borough = [], {}
    sel = selection.copy()
    for idx, row in sel.loc[sel["eligible"]].sort_values("candidate_rank").iterrows():
        if len(chosen) == n:
            break
        if per_borough.get(row.borough, 0) >= max_per_borough:
            sel.at[idx, "selection_note"] = "Eligible, skipped (borough cap)"
            continue
        if scorable.get(row.tds, 0) < MIN_SCORABLE_MONTHS:
            sel.at[idx, "selection_note"] = (f"Eligible, replaced: only {scorable.get(row.tds, 0)} "
                                             f"scorable test months (data unavailable)")
            continue
        chosen.append(row.tds)
        per_borough[row.borough] = per_borough.get(row.borough, 0) + 1
        sel.at[idx, "selected"] = True
        sel.at[idx, "selection_note"] = "Selected"
    return sel


def _fit(y: pd.Series, order, seasonal_order):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return SARIMAX(np.log(y), order=order, seasonal_order=seasonal_order,
                       enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)


def choose_order(y_train: pd.Series):
    """Small AIC grid on the training data only (log scale, one seasonal difference)."""
    best = None
    for p, q, P, Q in itertools.product([0, 1], [0, 1], [0, 1], [0, 1]):
        order, sorder = (p, 0, q), (P, 1, Q, 12)
        try:
            res = _fit(y_train, order, sorder)
        except Exception:  # noqa: BLE001 - some combinations fail to converge
            continue
        if np.isfinite(res.aic) and (best is None or res.aic < best[0]):
            best = (res.aic, order, sorder)
    if best is None:
        return config.SARIMA_ORDER, config.SARIMA_SEASONAL_ORDER
    return best[1], best[2]


def rolling_evaluation(y: pd.Series, test_start: pd.Timestamp, order, seasonal_order) -> pd.DataFrame:
    """One-step-ahead forecasts for each month from ``test_start`` to the end of ``y``."""
    rows = []
    for t in y.index[y.index >= test_start]:
        history = y.loc[y.index < t]
        baseline = history.get(t - pd.DateOffset(years=1), np.nan)
        res = _fit(history, order, seasonal_order)
        fc = res.get_forecast(1)
        ci = np.exp(fc.conf_int(alpha=0.2).iloc[0].to_numpy())
        rows.append(dict(revenue_month=t, actual=y.loc[t], baseline=baseline,
                         sarima=float(np.exp(fc.predicted_mean.iloc[0])), sarima_lo80=ci[0], sarima_hi80=ci[1]))
    return pd.DataFrame(rows)


def score(df: pd.DataFrame, pred: str) -> dict:
    e = (df["actual"] - df[pred]).abs()
    return {"mae": e.mean(), "wape": e.sum() / df["actual"].abs().sum()}


def run(dm: pd.DataFrame, train_end_year: int, test_year: int):
    """Returns (selection, predictions, metrics, outlook)."""
    selection = _pick(select_developments(dm, train_end_year), dm, test_year, config.N_FORECAST_DEVELOPMENTS)
    test_start = pd.Timestamp(test_year, 1, 1)
    preds, metrics, outlook = [], [], []
    for _, dev in selection.loc[selection["selected"]].iterrows():
        d = dm.loc[dm["tds"] == dev.tds].set_index("revenue_month").sort_index()
        y = d["kwh"].astype(float)
        y.index.freq = "MS"
        order, sorder = choose_order(y.loc[y.index < test_start])

        # Score only test months with complete coverage; incomplete months (missing or
        # a meter-count change) measure data gaps, not forecast skill.
        ev = rolling_evaluation(y.dropna(), test_start, order, sorder)
        cov = d.loc[ev["revenue_month"], ["is_missing_month", "flag_meter_count_change", "n_meters"]].reset_index(drop=True)
        ev["scored"] = ~(cov["is_missing_month"] | cov["flag_meter_count_change"]).to_numpy() & (ev["actual"] > 0)
        ev = ev.assign(tds=dev.tds, development_name=dev.development_name, borough=dev.borough)
        preds.append(ev)

        scored = ev.loc[ev["scored"]]
        b, s = score(scored, "baseline"), score(scored, "sarima")
        seasonal_rw = order == (0, 0, 0) and sorder[:3] == (0, 1, 0)
        if np.isclose(s["wape"], b["wape"], rtol=1e-6):
            winner = "Seasonal naive"
            note = ("Tie: AIC selected a seasonal random walk, which reproduces the baseline; "
                    "simpler baseline kept" if seasonal_rw else "Tie: simpler baseline kept")
        else:
            winner = "SARIMA" if s["wape"] < b["wape"] else "Seasonal naive"
            note = f"{winner} has lower WAPE"
        metrics.append(dict(tds=dev.tds, development_name=dev.development_name, borough=dev.borough,
                            sarima_order=f"{order}x{sorder}", months_scored=len(scored),
                            months_not_scored=12 - len(scored),
                            baseline_mae=b["mae"], baseline_wape=b["wape"],
                            sarima_mae=s["mae"], sarima_wape=s["wape"], selected_method=winner,
                            selection_reason=note))

        # Forward outlook for the next 12 months with the selected method, fitted on all data.
        hist = y.loc[y.index <= pd.Timestamp(test_year, 12, 1)].dropna()
        future = pd.date_range(hist.index[-1] + pd.offsets.MonthBegin(1), periods=12, freq="MS")
        if winner == "SARIMA":
            fc = _fit(hist, order, sorder).get_forecast(12)
            mean = np.exp(fc.predicted_mean.to_numpy())
            ci = np.exp(fc.conf_int(alpha=0.2).to_numpy())
            lo, hi = ci[:, 0], ci[:, 1]
        else:
            # Seasonal naive: last complete observation of the same calendar month.
            last = hist.groupby(hist.index.month).last()
            mean = np.array([last.get(m.month, np.nan) for m in future])
            lo = hi = np.full(12, np.nan)
        outlook.append(pd.DataFrame(dict(tds=dev.tds, development_name=dev.development_name, borough=dev.borough,
                                         revenue_month=future, method=winner, forecast_kwh=mean,
                                         forecast_lo80=lo, forecast_hi80=hi)))
    return selection, pd.concat(preds, ignore_index=True), pd.DataFrame(metrics), pd.concat(outlook, ignore_index=True)


def spending_scenarios(outlook: pd.DataFrame, dm: pd.DataFrame, annual: pd.DataFrame, test_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Planning estimate = forecast kWh x effective-cost assumption (not a bill forecast).

    Base: each development's effective cost in the same calendar month of the
          latest complete year (captures seasonal rate differences).
    Low:  base scaled to the lowest annual portfolio effective cost in the window.
    High: base increased by the largest annual portfolio effective-cost increase in the window.
    """
    last = dm.loc[dm["year"] == test_year, ["tds", "month", "effective_cost_per_kwh"]]
    # Fall back to the development's annual effective cost if a month is missing / zero kWh.
    annual_dev = dm.loc[dm["year"] == test_year].groupby("tds").apply(
        lambda g: g["cost"].sum() / g["kwh"].sum(), include_groups=False).rename("annual_rate")
    o = outlook.assign(month=outlook["revenue_month"].dt.month).merge(last, on=["tds", "month"], how="left")
    o = o.merge(annual_dev, on="tds", how="left")
    o["base_rate"] = o["effective_cost_per_kwh"].where(o["effective_cost_per_kwh"].between(0.02, 1.0), o["annual_rate"])

    latest_rate = annual.loc[annual["year"] == test_year, "effective_cost_per_kwh"].iat[0]
    low_factor = annual["effective_cost_per_kwh"].min() / latest_rate
    high_factor = 1 + annual["rate_yoy"].max()
    o["cost_low"] = o["forecast_kwh"] * o["base_rate"] * low_factor
    o["cost_base"] = o["forecast_kwh"] * o["base_rate"]
    o["cost_high"] = o["forecast_kwh"] * o["base_rate"] * high_factor
    assumptions = pd.DataFrame([
        dict(scenario="Low", factor=low_factor,
             basis=f"Lowest annual portfolio effective cost {annual['effective_cost_per_kwh'].min():.4f} $/kWh "
                   f"relative to {test_year} ({latest_rate:.4f})"),
        dict(scenario="Base", factor=1.0, basis=f"Each development's same-month {test_year} effective cost"),
        dict(scenario="High", factor=high_factor,
             basis=f"Largest annual portfolio effective-cost increase in the window ({annual['rate_yoy'].max():+.1%})"),
    ])
    return o.drop(columns=["effective_cost_per_kwh"]), assumptions
