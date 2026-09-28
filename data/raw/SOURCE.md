# Source file provenance

| Item | Value |
|---|---|
| Dataset | NYC Open Data — Electric Consumption and Cost (`jr24-e7cr`) |
| Portal page | https://data.cityofnewyork.us/Housing-Development/Electric-Consumption-And-Cost-2010-Sep-2025-/jr24-e7cr |
| File used for the committed results | Official CSV export covering revenue months **2010-01 to 2023-01** |
| Rows | 445,111 (27 columns, headers identical to the portal export) |
| MD5 | `30f91c320c5c3aef05b280a150b8662d` |
| How it was obtained | The analysis environment could not reach the portal, so a byte-level copy of an earlier official export (published in a public GitHub repository) was used. Column set and values match the portal schema. |

**Current release.** The catalog lists coverage through September 2025 (updated 2026-02-09).
Running `python scripts/download_data.py` replaces this file and this note with the current release. The
pipeline then sets the analysis window automatically (2019 through the last complete year), so the
forecast design becomes train 2019–2023 / test 2024.

The raw CSV is not committed to the repository.
