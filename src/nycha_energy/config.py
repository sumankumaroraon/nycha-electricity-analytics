"""Central configuration: paths, analysis window and quality thresholds.

The analysis window is derived from the data by default so that the same code
reproduces the intended design on any refresh of the source file:

* ``START_YEAR``: first year of the analysis window (2019).
* ``END_YEAR``: the last calendar year for which all twelve revenue months are
  present in the file. On the September 2025 release this is 2024; on older
  snapshots it is earlier. Override with the ``NYCHA_END_YEAR`` environment
  variable if needed.
* The forecast test year is ``END_YEAR``; training covers
  ``START_YEAR``..``END_YEAR - 1``.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
SQL_DIR = ROOT / "sql"

RAW_CSV = Path(os.getenv("NYCHA_RAW_CSV", DATA_RAW / "Electric_Consumption_And_Cost.csv"))

SOURCE_URL = (
    "https://data.cityofnewyork.us/Housing-Development/"
    "Electric-Consumption-And-Cost-2010-Sep-2025-/jr24-e7cr"
)
SOURCE_CSV_URL = "https://data.cityofnewyork.us/api/views/jr24-e7cr/rows.csv?accessType=DOWNLOAD"

START_YEAR = int(os.getenv("NYCHA_START_YEAR", 2019))
END_YEAR_OVERRIDE = os.getenv("NYCHA_END_YEAR")

# --- Data-quality thresholds -------------------------------------------------
# Row-level effective cost per kWh outside these percentiles (computed on rows
# with positive kWh and positive cost inside the analysis window) is flagged.
EXTREME_RATE_LOWER_PCT = 0.005
EXTREME_RATE_UPPER_PCT = 0.995
# Service periods outside this range (days) are flagged as unusual.
MIN_SERVICE_DAYS, MAX_SERVICE_DAYS = 20, 45
# A development-month whose reporting meter count differs from the development's
# typical (median) count by more than this share is flagged as a coverage change.
METER_COUNT_TOLERANCE = 0.10

# --- Anomaly thresholds ------------------------------------------------------
ROBUST_Z_THRESHOLD = 3.5          # modified z-score on same-month history
MATERIAL_COST_CHANGE = 10_000     # USD; minimum absolute YoY change to prioritise
STABLE_KWH_BAND = 0.05            # |YoY kWh change| <= 5% counts as "stable"

# --- Forecasting -------------------------------------------------------------
N_FORECAST_DEVELOPMENTS = 5
SARIMA_ORDER = (1, 0, 0)
SARIMA_SEASONAL_ORDER = (0, 1, 1, 12)

RANDOM_SEED = 42
