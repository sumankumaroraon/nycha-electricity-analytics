"""Download the current NYC Open Data release and record its provenance.

    python scripts/download_data.py

Writes data/raw/Electric_Consumption_And_Cost.csv and data/raw/SOURCE.md
(download date, URL, MD5, row count and revenue-month coverage).
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nycha_energy import config  # noqa: E402


def main() -> None:
    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    target = config.DATA_RAW / "Electric_Consumption_And_Cost.csv"
    print(f"Downloading {config.SOURCE_CSV_URL}\n  -> {target}")
    urllib.request.urlretrieve(config.SOURCE_CSV_URL, target)

    md5 = hashlib.md5(target.read_bytes()).hexdigest()
    months = pd.read_csv(target, usecols=["Revenue Month"], dtype=str)["Revenue Month"]
    (config.DATA_RAW / "SOURCE.md").write_text(f"""# Source file provenance

| Item | Value |
|---|---|
| Dataset | NYC Open Data — Electric Consumption and Cost (`jr24-e7cr`) |
| Portal page | {config.SOURCE_URL} |
| Download URL | {config.SOURCE_CSV_URL} |
| Download date (UTC) | {datetime.now(timezone.utc):%Y-%m-%d %H:%M} |
| File | `{target.name}` |
| MD5 | `{md5}` |
| Rows | {len(months):,} |
| Revenue months | {months.min()} to {months.max()} |

The raw CSV is not committed (size and licensing hygiene). Re-download with
`python scripts/download_data.py`, then rerun the pipeline.
""")
    print(f"Done: {len(months):,} rows, revenue months {months.min()} to {months.max()}, MD5 {md5}")


if __name__ == "__main__":
    main()
