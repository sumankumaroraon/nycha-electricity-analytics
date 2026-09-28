"""Build the static HTML dashboard (docs/index.html) from data/processed/.

The page is fully self-contained apart from Chart.js and a web font loaded from CDNs,
so it can be served by GitHub Pages straight from the /docs folder.

    PYTHONPATH=src python -m nycha_energy.dashboard
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"
OUTPUT = config.ROOT / "docs" / "index.html"
REPO_URL = "https://github.com/sumankumaroraon/nycha-electricity-analytics"


def _num(v, nd=0):
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
        return None
    return round(float(v), nd) if nd else int(round(float(v)))


def build_payload(processed: Path = config.DATA_PROCESSED) -> dict:
    fm = pd.read_csv(processed / "fact_development_month.csv", parse_dates=["revenue_month"])
    months = sorted(fm["revenue_month"].unique())
    month_idx = {m: i for i, m in enumerate(months)}
    devs = (fm[["tds", "development_name", "borough"]].drop_duplicates("tds")
              .sort_values("development_name").reset_index(drop=True))

    series = {}
    for tds, g in fm.groupby("tds"):
        g = g.sort_values("revenue_month")
        miss = g["is_missing_month"].to_numpy()

        def arr(col):
            return [None if m else _num(v) for v, m in zip(g[col].to_numpy(), miss)]
        series[str(tds)] = {"k": arr("kwh"), "c": arr("cost"), "e": arr("kwh_charges"),
                            "d": arr("kw_charges"), "o": arr("other_charges")}

    inv = pd.read_csv(processed / "investigation_table.csv", parse_dates=["revenue_month"])
    inv = inv[inv["is_primary"]].copy()
    issues = sorted(inv["issue"].unique())
    expl = sorted(inv["possible_explanation"].unique())
    inv_rows = [[r.investigation_id, int(r.tds), month_idx[r.revenue_month], issues.index(r.issue),
                 _num(r.financial_magnitude), r.evidence, expl.index(r.possible_explanation),
                 None if pd.isna(r.top_record_id) else int(r.top_record_id)]
                for r in inv.itertuples()]

    fmet = pd.read_csv(processed / "forecast_metrics.csv")
    bt = pd.read_csv(processed / "forecast_backtest.csv", parse_dates=["revenue_month"])
    out = pd.read_csv(processed / "forecast_outlook.csv", parse_dates=["revenue_month"])
    assumptions = pd.read_csv(processed / "scenario_assumptions.csv")
    meta = json.loads((config.REPORTS / "run_metadata.json").read_text())

    forecast = []
    for r in fmet.itertuples():
        b = bt[bt["tds"] == r.tds].sort_values("revenue_month")
        o = out[out["tds"] == r.tds].sort_values("revenue_month")
        forecast.append({
            "tds": int(r.tds), "name": r.development_name, "borough": r.borough, "order": r.sarima_order,
            "method": r.selected_method, "reason": r.selection_reason, "scored": int(r.months_scored),
            "mae": [_num(r.baseline_mae), _num(r.sarima_mae)], "wape": [_num(r.baseline_wape, 4), _num(r.sarima_wape, 4)],
            "bt": {"m": b["revenue_month"].dt.strftime("%Y-%m").tolist(), "a": [_num(v) for v in b["actual"]],
                   "b": [_num(v) for v in b["baseline"]], "s": [_num(v) for v in b["sarima"]],
                   "ok": b["scored"].astype(bool).tolist()},
            "out": {"m": o["revenue_month"].dt.strftime("%Y-%m").tolist(), "k": [_num(v) for v in o["forecast_kwh"]],
                    "lo": [_num(v) for v in o["cost_low"]], "base": [_num(v) for v in o["cost_base"]],
                    "hi": [_num(v) for v in o["cost_high"]]},
        })

    ex = pd.read_csv(processed / "exclusion_log.csv")
    return {
        "meta": {**meta, "repo": REPO_URL},
        "months": [pd.Timestamp(m).strftime("%Y-%m") for m in months],
        "devs": [[int(r.tds), r.development_name, r.borough] for r in devs.itertuples()],
        "series": series,
        "issues": issues, "explanations": expl, "inv": inv_rows,
        "forecast": forecast,
        "scenarios": assumptions[["scenario", "factor", "basis"]].to_dict("records"),
        "quality": {"excluded": ex["reason"].value_counts().to_dict(),
                    "excluded_cost": _num(ex["current_charges"].sum())},
    }


def build(output: Path = OUTPUT) -> Path:
    payload = json.dumps(build_payload(), separators=(",", ":"), ensure_ascii=False)
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    (output.parent / ".nojekyll").touch()
    return output


if __name__ == "__main__":
    p = build()
    print(f"Dashboard written to {p.relative_to(config.ROOT)} ({p.stat().st_size / 1e6:.1f} MB)")
