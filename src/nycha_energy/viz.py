"""Static charts for the README, notebooks and memo (the HTML dashboard holds the interactive versions)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import pandas as pd  # noqa: E402
import re  # noqa: E402

INK, MUTED, GRID = "#1F2933", "#7B8794", "#E4E7EB"
BLUE, TEAL, AMBER, RED, GREEN = "#1F5A96", "#2A9D8F", "#E9A23B", "#C0392B", "#2E7D32"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
    "legend.frameon": False,
})

usd_m = mtick.FuncFormatter(lambda x, _: f"${x / 1e6:,.0f}M")
usd_k = mtick.FuncFormatter(lambda x, _: f"${x / 1e3:,.0f}K")
gwh = mtick.FuncFormatter(lambda x, _: f"{x / 1e6:,.0f}")


usd_m1 = mtick.FuncFormatter(lambda x, _: f"${x / 1e6:,.1f}M")


def nice_name(name: str) -> str:
    """Title-case a development name while keeping Roman numerals and initialisms."""
    words = []
    for w in str(name).split(" "):
        core = w.strip("()")
        if re.fullmatch(r"[IVX]+", core) or re.fullmatch(r"[A-Z]\.?", core):
            words.append(w)
        else:
            words.append(w.title())
    return " ".join(words)


def _note(fig, text):
    fig.text(0.01, -0.02, text, fontsize=8, color=MUTED, ha="left", va="top")


def portfolio_trend(pm: pd.DataFrame, path, tolerance=0.10):
    fig, ax = plt.subplots(figsize=(10, 4.4))
    med = pm["meters_reporting"].median()
    for m in pm.loc[pm["meters_reporting"] < med * (1 - tolerance), "revenue_month"]:
        ax.axvspan(m - pd.Timedelta(days=15), m + pd.Timedelta(days=15), color=GRID, alpha=0.9, zorder=0)
    ax.bar(pm["revenue_month"], pm["kwh"], width=25, color=BLUE, alpha=0.85, label="Consumption (GWh)")
    ax.yaxis.set_major_formatter(gwh)
    ax.set_ylabel("GWh per month")
    ax2 = ax.twinx()
    ax2.plot(pm["revenue_month"], pm["effective_cost_per_kwh"], color=AMBER, lw=2.2, label="Effective cost ($/kWh)")
    ax2.set_ylabel("Effective cost ($/kWh)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax2.yaxis.set_major_formatter(mtick.FormatStrFormatter("$%.2f"))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=9)
    ax.set_title("Portfolio electricity consumption and effective cost per kWh", pad=26)
    _note(fig, "Effective cost = total reported charges / total kWh (includes demand and other bill components; not a tariff).\n"
               "Grey shading = months with >10% fewer reporting meters than usual (totals understated by missing bills).")
    fig.savefig(path)
    plt.close(fig)


def waterfall(wf: pd.DataFrame, path, subtitle=""):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    running, bottoms, colors = 0.0, [], []
    for _, r in wf.iterrows():
        if r.kind == "total":
            bottoms.append(0)
            running = r.amount
            colors.append(BLUE)
        else:
            bottoms.append(running if r.amount >= 0 else running + r.amount)
            running += r.amount
            colors.append(RED if r.amount > 0 else GREEN)
    heights = wf["amount"].abs().to_numpy()
    labels = [s.replace(" (", "\n(").replace(" effect", "\neffect") for s in wf["step"]]
    ax.bar(labels, heights, bottom=bottoms, color=colors, width=0.6)
    tops = [b + h for b, h in zip(bottoms, heights)]
    totals = wf.loc[wf["kind"] == "total", "amount"]
    for i in range(len(tops) - 1):  # connector lines
        level = tops[i] if (wf["kind"].iat[i] == "total" or wf["amount"].iat[i] >= 0) else bottoms[i]
        ax.plot([i + 0.3, i + 0.7], [level, level], color=MUTED, lw=0.8)
    for i, (r, b, h) in enumerate(zip(wf.itertuples(), bottoms, heights)):
        b = max(b, totals.min() * 0.85)
        h = (bottoms[i] + heights[i]) - b
        label = f"${r.amount / 1e6:,.1f}M" if r.kind == "total" else f"{'+' if r.amount >= 0 else '−'}${abs(r.amount) / 1e6:,.1f}M"
        ax.text(i, b + h, label, ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(totals.min() * 0.85, max(tops) * 1.03)
    ax.yaxis.set_major_formatter(usd_m)
    ax.tick_params(axis="x", labelsize=9)
    ax.set_title("What changed electricity spending year over year" + (f" — {subtitle}" if subtitle else ""))
    _note(fig, "Accounting decomposition at development × month level. Axis does not start at zero. "
               "Not evidence of a tariff change.")
    fig.savefig(path)
    plt.close(fig)


def bill_components(annual: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(8, 4))
    years = annual["year"].astype(str)
    b = 0
    for col, lab, colr in [("kwh_charges", "kWh (energy) charges", BLUE), ("kw_charges", "kW (demand) charges", TEAL),
                           ("other_charges", "Other charges", AMBER)]:
        ax.bar(years, annual[col], bottom=b, label=lab, color=colr, width=0.6)
        b = b + annual[col]
    ax.yaxis.set_major_formatter(usd_m)
    ax.legend(loc="upper left", ncol=3)
    ax.set_ylim(0, b.max() * 1.15)
    ax.set_title("Reported bill components by year")
    fig.savefig(path)
    plt.close(fig)


def concentration(dy: pd.DataFrame, year: int, path, top=15, extra_note=""):
    d = dy.loc[dy["year"] == year].sort_values("cost", ascending=False)
    d["cum_share"] = d["share_of_portfolio_cost"].cumsum()
    t = d.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.barh(t["development_name"].map(nice_name), t["cost"], color=BLUE)
    ax.xaxis.set_major_formatter(usd_m1)
    for y, (c, s) in enumerate(zip(t["cost"], t["share_of_portfolio_cost"])):
        ax.text(c, y, f"  {s:.1%}", va="center", fontsize=8, color=INK)
    n80 = int((d["cum_share"] < 0.8).sum() + 1)
    ax.set_title(f"Top {top} developments by electricity spending, {year}")
    _note(fig, f"Labels show share of portfolio spending. {n80} of {len(d)} developments account for 80% of {year} spending." + (f"\n{extra_note}" if extra_note else ""))
    fig.savefig(path)
    plt.close(fig)


def forecast_backtest(pred: pd.DataFrame, metrics: pd.DataFrame, dm: pd.DataFrame, path):
    devs = metrics["tds"].tolist()
    fig, axes = plt.subplots(len(devs), 1, figsize=(10, 2.3 * len(devs)), sharex=True)
    for ax, tds in zip(axes, devs):
        h = dm.loc[dm["tds"] == tds]
        p = pred.loc[pred["tds"] == tds]
        m = metrics.loc[metrics["tds"] == tds].iloc[0]
        ax.plot(h["revenue_month"], h["kwh"], color=INK, lw=1.4, label="Actual")
        ax.plot(p["revenue_month"], p["baseline"], color=TEAL, lw=1.6, ls="--", marker="o", ms=3, label="Seasonal naive")
        ax.plot(p["revenue_month"], p["sarima"], color=AMBER, lw=1.6, marker="s", ms=3, label="SARIMA")
        ax.axvline(p["revenue_month"].min(), color=MUTED, lw=0.8, ls=":")
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x / 1e6:.1f}"))
        ax.set_title(f"{nice_name(m.development_name)} ({m.borough.title()}) — WAPE baseline {m.baseline_wape:.1%} | "
                     f"SARIMA {m.sarima_wape:.1%} → {m.selected_method}", fontsize=10)
        ax.set_ylabel("GWh")
    axes[0].legend(loc="upper left", ncol=3, fontsize=8)
    fig.suptitle("Rolling one-month-ahead backtest (dotted line = start of test year)", x=0.01, ha="left",
                 fontweight="bold", fontsize=12)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def data_quality(counts: dict, flag_counts: pd.Series, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1, 1.6]})
    ex = pd.Series({"Exact duplicates": counts["exact_duplicates"], "Superseded bill versions": counts["superseded_bills"],
                    "Same-bill near duplicates": counts["near_duplicates_same_bill"]})
    axes[0].barh(ex.index, ex.values, color=RED)
    axes[0].set_title("Excluded records")
    for y, v in enumerate(ex.values):
        axes[0].text(v, y, f" {v:,}", va="center", fontsize=8)
    f = flag_counts.sort_values()
    axes[1].barh(f.index, f.values, color=AMBER)
    axes[1].set_title("Flagged and retained records")
    for y, v in enumerate(f.values):
        axes[1].text(v, y, f" {v:,}", va="center", fontsize=8)
    for ax in axes:
        ax.set_xscale("log")
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
