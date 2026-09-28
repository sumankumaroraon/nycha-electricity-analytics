"""Dashboard payload checks. Uses the committed data/processed outputs; skipped if they are absent."""
import pytest

from nycha_energy import config, dashboard

pytestmark = pytest.mark.skipif(not (config.DATA_PROCESSED / "fact_development_month.csv").exists(),
                                reason="processed outputs not present")


def test_template_has_data_placeholder():
    assert "/*__DATA__*/null" in dashboard.TEMPLATE.read_text(encoding="utf-8")


def test_payload_totals_match_fact_table():
    import pandas as pd
    p = dashboard.build_payload()
    fm = pd.read_csv(config.DATA_PROCESSED / "fact_development_month.csv")
    embedded = sum(v for s in p["series"].values() for v in s["c"] if v is not None)
    assert embedded == pytest.approx(fm["cost"].sum(), rel=1e-6)   # rounding to whole dollars only
    assert len(p["devs"]) == fm["tds"].nunique()
    assert all(len(s["k"]) == len(p["months"]) for s in p["series"].values())


def test_payload_is_json_serialisable():
    import json
    json.dumps(dashboard.build_payload())
