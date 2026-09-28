"""Unit tests on small hand-built cases (no source data required)."""
import numpy as np
import pandas as pd
import pytest

from nycha_energy import analysis, prepare


def _records(rows):
    base = dict(development_name="DEV A", borough="BRONX", account_name="A", location="BLD 01", meter_amr="NONE",
                meter_scope=None, tds=1, edp="1", rc_code="X", funding_source="FEDERAL", amp="A1",
                vendor_name="NYPA", umis_bill_id=100, revenue_month=pd.Timestamp("2021-01-01"),
                service_start=pd.Timestamp("2020-12-01"), service_end=pd.Timestamp("2020-12-31"), service_days=30.0,
                meter_number="M1", estimated="N", current_charges=100.0, rate_class="R", bill_analyzed="Yes",
                kwh=1000.0, kwh_charges=40.0, kw=0.0, kw_charges=0.0, other_charges=60.0)
    df = pd.DataFrame([{**base, **r} for r in rows])
    df.insert(0, "record_id", np.arange(1, len(df) + 1))
    return df


def test_exact_duplicate_is_excluded():
    kept, excl = prepare._deduplicate(_records([{}, {}]))
    assert len(kept) == 1 and excl.reason.tolist() == ["exact_duplicate"]


def test_reissued_bill_keeps_highest_bill_id():
    kept, excl = prepare._deduplicate(_records([{"umis_bill_id": 100, "current_charges": 90.0},
                                                {"umis_bill_id": 200, "current_charges": 120.0}]))
    assert kept.umis_bill_id.tolist() == [200]
    assert excl.reason.tolist() == ["superseded_bill"]


def test_two_meters_same_month_are_not_duplicates():
    kept, excl = prepare._deduplicate(_records([{"meter_number": "M1"}, {"meter_number": "M2"}]))
    assert len(kept) == 2 and excl.empty


def test_two_service_periods_same_month_are_both_kept():
    kept, _ = prepare._deduplicate(_records([{}, {"service_start": pd.Timestamp("2021-01-01"),
                                                  "service_end": pd.Timestamp("2021-01-15"), "umis_bill_id": 101}]))
    assert len(kept) == 2


def test_flags_demand_only_and_credit():
    df, _ = prepare._flag(_records([{"kwh": 0.0, "kw": 50.0, "current_charges": 300.0},
                                    {"current_charges": -25.0}] + [{}] * 10))
    assert df.flag_demand_only.iat[0] and df.flag_zero_kwh_positive_cost.iat[0]
    assert df.flag_negative_cost.iat[1]
    assert np.isnan(df.row_rate.iat[0])  # no rate when kWh = 0


def _panel(q0, c0, q1, c1):
    return pd.DataFrame({
        "tds": [1, 1], "development_name": ["A", "A"], "borough": ["BRONX"] * 2, "month": [1, 1],
        "year": [2021, 2022], "kwh": [q0, q1], "cost": [c0, c1], "is_missing_month": [q0 is None, q1 is None]})


@pytest.mark.parametrize("q0,c0,q1,c1", [(1000, 150, 1100, 190), (1000, 150, 800, 160), (500, 40, 500, 60)])
def test_decomposition_sums_to_cost_change(q0, c0, q1, c1):
    d = analysis.yoy_decomposition(_panel(q0, c0, q1, c1), 2022).iloc[0]
    assert d.comparable
    assert d.consumption_effect == pytest.approx((q1 - q0) * c0 / q0)
    assert d.consumption_effect + d.rate_effect == pytest.approx(c1 - c0)


def test_decomposition_zero_kwh_goes_to_non_comparable():
    d = analysis.yoy_decomposition(_panel(0, 50, 1000, 150), 2022).iloc[0]
    assert not d.comparable and d.non_comparable_change == pytest.approx(100)
    b = analysis.bridge(analysis.yoy_decomposition(_panel(0, 50, 1000, 150), 2022)).iloc[0]
    assert b.prior_cost + b.consumption_effect + b.rate_effect + b.non_comparable_change == pytest.approx(b.current_cost)


def test_effective_cost_is_ratio_of_totals_not_mean_of_ratios():
    recs = _records([{"kwh": 1000.0, "current_charges": 100.0},
                     {"meter_number": "M2", "kwh": 9000.0, "current_charges": 1800.0}])
    flagged, _ = prepare._flag(recs.assign(n_versions_same_period=1))
    dm = prepare.development_month(flagged, 2021, 2021)
    jan = dm[dm.revenue_month == "2021-01-01"].iloc[0]
    assert jan.effective_cost_per_kwh == pytest.approx(1900 / 10000)   # not mean(0.10, 0.20) = 0.15
    assert dm.is_missing_month.sum() == 11                             # complete panel keeps gaps visible
