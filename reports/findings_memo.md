# Memo: Electricity spending drivers and planning outlook

**To:** Energy & Utilities Management (illustrative audience) · **From:** Suman Oraon, Data Analyst
**Scope:** 335 NYCHA developments, 2022 vs 2021 · **Source:** NYC Open Data *Electric Consumption and Cost*
(release covering revenue months through Jan 2023; see README for refresh)

**Bottom line:** 2022 electricity spending rose **$11.2M (+6.4%) to $185.7M** while reported consumption fell
6.7%. Like-for-like, consumption barely moved. The increase is an *effective-cost* story, and about a third of it
comes from one suspect bill record.

### Findings

**1. Higher cost per kWh, not higher consumption, drove spending.** On the 3,927 development-months reported in both
years, kWh fell **2.8%** while cost rose **10.7%**. The effective cost went from **$0.151 to $0.172 per kWh (+14%)**.
The year-over-year bridge breaks down as follows:

- Consumption effect: **−$2.5M**
- Effective-cost effect: **+$20.5M**
- Non-comparable months: **−$6.8M**

Among bill components, *other charges* rose **$10.2M (+9.9%)**, compared with energy charges +2.0% and demand charges +0.4%.
This is an accounting decomposition. It does not show that a tariff changed.

**2. A single record accounts for about a third of the increase.** Record #18453 (West Brighton II, July 2022)
bills **$3.55M for 69,491 kWh**, about $51/kWh against roughly $0.19 expected. The same meter bills $4–6K in adjacent months,
and this one line makes West Brighton II the portfolio's top-spending development. **Excluding it, 2022 cost growth is
+4.4%.** A second pattern, a dollar amount apparently keyed into the kWh field (Morrisania, Nov 2021), distorts
year-over-year comparisons for that development. Both require investigation.

**3. Reporting gaps overstate the drop in demand.** **20 developments** have missing months in 2022. Six are absent
for 11–12 months: Ocean Bay (Bayside), Albany, Albany II, Washington, Sheepshead Bay and Ravenswood. Late-2022 months
also have fewer meters reporting. Separately, **6,407 re-issued bill versions** were resolved to the latest version;
summing them instead would overstate 2019–2022 spending by about **$11M (+1.8%)**.

**Forecast.** For five stable, high-volume developments, a same-month-last-year baseline matched or beat SARIMA at
four (pooled WAPE 8.5% vs 8.6%). The next-12-month **planning estimate** is **69.4 GWh**, costing **$12.0M in the base case,
within a range of $8.5M–$14.5M**. The range reflects historical effective-cost scenarios, not a bill forecast.

### Recommended actions

1. **Validate record #18453 with billing.** If it is an error, request a correction or credit. Add a pre-booking check that
   holds any line above the 99.5th-percentile cost per kWh (about $0.38) for review.
2. **Explain the "other charges" increase** before attributing it to price. Start by pulling bill detail for the
   developments with the largest effective-cost effect in `investigation_table.csv`.
3. **Report consumption like-for-like with a coverage indicator.** Confirm the status of the six developments
   absent for most of 2022 before treating the decline as demand reduction.
4. **Plan with the seasonal baseline × base effective cost, using the low/high band.** Re-test SARIMA once a longer
   history (the current release through 2025) is loaded.
