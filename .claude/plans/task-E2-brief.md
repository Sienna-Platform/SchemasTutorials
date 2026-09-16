# Task E2 — Existing devices and supply technologies (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md` (its "Global
constraints" and "What the dataset does and does not support" sections
bind on this task too). Progress ledger:
`.claude/plans/2026-09-01-capacity-expansion-progress.md` — Task E1 is
already done; read its ledger entry and
`.claude/plans/task-E1-report.md` before starting, since you build
directly on E1's output.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`julia/`, and do not modify any file under `python/src/rts_gmlc_case/`
except adding the two new files below (nothing existing needs editing for
this task — if you find you need to change an existing file, stop and
report NEEDS_CONTEXT rather than guessing).

## What E1 already gave you

`python/src/rts_gmlc_case/investments/topology.py`:
`add_investment_topology(doc, source, idx) -> InvestmentTopologyIndex`,
with fields `node_id_by_bus_number: dict[int, int]`,
`zone_id_by_name: dict[str, int]`, `zone_id_by_bus_number: dict[int,
int]`. `python/src/rts_gmlc_case/investments/data.py`:
`investments_source_dir() -> Path` (validates
`data/RTS-investments/` is present; already downloaded in this checkout).
`python/src/rts_gmlc_case/document.py`:
`CaseDocument.add_supplemental_attribute(model, *, component_id,
component_type) -> int` — use this for `ExistingDevices`, exactly the way
E1 used it for `TopologyMapping` (read
`python/src/rts_gmlc_case/investments/topology.py` for the pattern before
writing anything).

## New files

- `python/src/rts_gmlc_case/investments/technologies.py`
- `python/src/rts_gmlc_case/investments/costs.py`
- `python/tests/test_investments_technologies.py`
- `python/tests/test_investments_costs.py` (or fold into the technologies
  test file if that reads more naturally — your call)

## Data source

`data/RTS-investments/capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv`
— every one of its 155 rows has `IsExistUnit == True` (verified: this file
is entirely existing devices, no candidate rows to filter out). Relevant
columns: `GEN UID` (unique device id, e.g. `"101_CT_1"`), `Bus ID`
(joins to the operations `bus.csv` / E1's `node_id_by_bus_number` and
`zone_id_by_bus_number`), `tech` (the technology-class key you bucket
by), `Unit Type`, `Fuel`, `cap` (MW).

Verified `tech` -> (`Unit Type`, `Fuel`) is a clean many-to-one mapping
(every row of a given `tech` has the same `Unit Type` and `Fuel`, except
`o-g-s` which spans `Unit Type` in `{CT, STEAM}` with `Fuel` always
`Oil`):

```
tech          Unit Type   Fuel       row count
distpv        RTPV        Solar      31
gas-ct        CT          NG         27
upv           PV          Solar      25
o-g-s         CT, STEAM   Oil        19
hydED         HYDRO       Hydro      19
coalolduns    STEAM       Coal       16
gas-cc        CC          NG         10
wind-ons      WIND        Wind        4
hydEND        ROR         Hydro       1
battery_4     STORAGE     Storage     1
nuclear       NUCLEAR     Nuclear     1
csp-ns        CSP         Solar       1
```

`python/src/rts_gmlc_case/generation.py` already has
`PRIME_MOVER_BY_UNIT_TYPE: dict[str, PrimeMovers]` and
`FUEL_BY_SOURCE: dict[str, ThermalFuels]` module-level constants (both
public, not underscore-prefixed) built for the *operations* `gen.csv`'s
`Unit Type`/`Fuel` columns. Their value sets already cover every `Unit
Type`/`Fuel` string this investments dataset uses (`PV`, `WIND`, `CSP`,
`HYDRO`, `ROR`, `STORAGE`, `NUCLEAR`, `STEAM`, `CT`, `CC`; `Oil`, `Coal`,
`NG`, `Nuclear`) — **reuse them by importing, don't redefine.** `Hydro`,
`Solar`, `Wind`, and `Storage` as `Fuel` values have no `FUEL_BY_SOURCE`
entry and don't need one: `SupplyTechnology.fuel` is only meaningful for
thermal classes (see below); leave it `None` for non-thermal classes.

## Which `tech` classes become `SupplyTechnology` candidates — read literally

The plan's exact words: *"`SupplyTechnology` candidates for the technology
classes the supply curves cover (`upv`, `wind-ons`), plus thermal and
hydro classes from the generator database."* Read as a set union, this
means exactly:

- `upv`, `wind-ons` (the two with a `supplycurvedata/*_supply_curve-reference_nodal.csv` file)
- thermal classes: `gas-cc`, `gas-ct`, `o-g-s`, `coalolduns`, `nuclear`
- hydro classes: `hydED`, `hydEND`

= **9 `SupplyTechnology` components**, one per class above. **`distpv` and
`csp-ns` are deliberately excluded** — neither has a supply curve file nor
counts as thermal/hydro. `battery_4` is excluded too — it becomes a
`StorageTechnology` in Task E3, not a `SupplyTechnology`; don't touch it
here beyond confirming it's absent from your output. If you read this
differently, that's a real ambiguity worth a ruling — state your reading
and reasoning in the report, but this literal reading is the controller's
default; deviate only if you find a concrete reason the CSVs make it
wrong.

## `power_systems_type` (R39 — verbatim from the plan)

*"`power_systems_type` takes the exact PSY type names this campaign
emits — `ThermalStandard`, `RenewableDispatch`, `HydroDispatch`,
`EnergyReservoirStorage`. Test that every value equals a type name
actually present in the document."* For E2's 9 classes:

- `gas-cc`, `gas-ct`, `o-g-s`, `coalolduns`, `nuclear` -> `"ThermalStandard"`
- `hydED`, `hydEND` -> `"HydroDispatch"`
- `upv`, `wind-ons` -> `"RenewableDispatch"`

The "type actually present in the document" check can only be a same-file
sanity assertion at this task's boundary (this task doesn't build a full
document with `ThermalStandard`/`HydroDispatch`/`RenewableDispatch`
components in it — those are the *operations* stages, already built by
`rts_gmlc_case.topology`/`.generation`, not part of this investments
branch). Write the test as: build a `CaseDocument`, run the full
**operations** pipeline stages your test needs
(`rts_gmlc_case.build.build_case` writes a whole case — reuse it, or the
individual operations stages, whichever is faster in a test) so the
operations component types exist in the same document, then run your new
investments stage on top and assert every `SupplyTechnology.power_systems_type`
equals a type name with at least one component under it in
`doc.document.components`. If building a full operations case per-test is
too slow for a non-`slow`-marked test, do the narrower thing: assert the
4 R39 type name strings are exactly `{"ThermalStandard", "HydroDispatch",
"RenewableDispatch", "EnergyReservoirStorage"}` against a constant, and
leave the "actually present in the document" cross-check to Task E6 (the
combined-document task), noting that choice in your report — Task E6's
brief will be told to pick this up if you defer it.

## `ExistingDevices` (supplemental attribute)

Per the schema (`SiennaSchemas/Investments/Attributes/ExistingDevices.json`):
*"Supplemental attribute mapping a technology in the portfolio to the
existing system — for example, the list of existing generators that
correspond to one supply technology."* One `ExistingDevices` per
`SupplyTechnology`, `existing_devices` = the sorted list of `GEN UID`
strings whose `tech` matches, attached via
`add_supplemental_attribute(existing_devices_model, component_id=<the
SupplyTechnology's id>, component_type="SupplyTechnology")` — same call
shape E1 used for `TopologyMapping` against `Zone`.

## `region` field

`SupplyTechnology.region: list[int] | None` — "Location where the
component applies. Can be a zone or node." Populate with the sorted list
of **zone ids** (via E1's `zone_id_by_bus_number`, looked up by each
device's `Bus ID`) where at least one existing device of that class sits
— i.e. the union of zones its `ExistingDevices` members belong to. No
class in this dataset is expected to be zone-universal; don't assume it
is.

## `costs.py` — the external-cost surface (R37)

**Critical, easy to get wrong:** the supply curve files' `supply_curve_cost_per_mw`
column (~$10k/MW, present for `upv`/`wind-ons`) is a **site
interconnection cost**, not a capital cost. Do **not** read it into
`SupplyTechnology.capital_costs` or anywhere financial. If you use those
supply curve files at all in this task (you may not need to — nothing
above requires them), keep that column untouched by cost logic.

Build one module, `costs.py`, holding:

- A module docstring stating plainly: these capital-cost and financial
  figures are **illustrative order-of-magnitude values approximating
  published NREL ATB ranges** (name a specific ATB edition and scenario
  you're approximating, e.g. "NREL 2024 Annual Technology Baseline,
  Moderate scenario, ~2030 vintage" or similar) — and that **no live data
  pull was performed this session**; a reader who needs verified numbers
  should replace this table from the actual ATB spreadsheet. This is the
  honest-provenance framing R37 requires — don't imply more precision
  than "plausible for RTS-scale technology-agnostic worked example."
- One `TechnologyFinancialData` instance per `SupplyTechnology` class (all
  6 fields required: `capital_recovery_period` (yr), `technology_base_year`,
  `debt_fraction`, `debt_rate`, `return_on_equity`, `tax_rate` — plausible
  values, e.g. 20-30yr recovery, ~50% debt fraction, mid-single-digit debt
  rate, high-single/low-double-digit ROE, ~21% tax rate — pick sensible
  numbers, they don't need per-class variation unless you want it).
- One capital cost (`ValueCurve`, USD/MW) per class — check
  `power_openapi_models.core.models.ValueCurve`'s shape before
  constructing one (it's a `RootModel` variant per `document.py`'s
  comment on `FunctionData`; find the simplest linear/constant variant
  that fits a flat $/MW figure and use that, don't invent structure).
  Order-of-magnitude figures to riff from (all illustrative, USD/MW):
  gas-cc ~1.0-1.3M, gas-ct ~0.7-1.0M, coalolduns ~4-5M (new coal is
  unrealistic in practice but this is a candidate slot, not a forecast),
  nuclear ~6-9M, hydED/hydEND ~4-6M, upv ~0.9-1.1M, wind-ons ~1.3-1.6M.
  Pick one number per class inside these bands (or state why you deviated)
  and put a one-line comment at each entry naming the class it's for.
- A per-entry comment (even one line) is enough — don't paragraph-pad.

## `add_supply_technologies(doc, source, idx, inv_idx) -> dict[str, int]`
### (in `technologies.py`; name/signature your call, but return the class-name -> minted-id map — later tasks will need it)

- `source` = `investments_source_dir()`'s return (E3/E4 will need it more
  than this task does; read the generator database from it).
- `idx` = the operations `TopologyIndex` (for cross-checks if needed).
- `inv_idx` = E1's `InvestmentTopologyIndex` (for `region` via
  `zone_id_by_bus_number`).
- Mint one `SupplyTechnology` + one `ExistingDevices` (as a supplemental
  attribute on it) per class, in sorted class-name order for determinism
  (same convention E1 used for zones).

## Verify

- Exactly 9 `SupplyTechnology` components, named/keyed by the 9 classes
  above (`distpv`, `csp-ns`, `battery_4` absent).
- Every `SupplyTechnology.power_systems_type` is one of the 4 R39 strings,
  correctly assigned per class per the table above.
- Every `ExistingDevices.existing_devices` list's `GEN UID` count matches
  that class's row count in the generator database CSV (e.g. `gas-ct` ->
  27 devices) — assert this against the CSV, not a hardcoded number.
- Every `SupplyTechnology.region` entry resolves to a zone id that exists
  in `inv_idx.zone_id_by_name.values()`.
- `financial_data` present and fully populated (no `None` where the
  schema requires a value) on every `SupplyTechnology`.
- `doc.validate()` still passes (it won't check `region` or supplemental
  attributes — that's expected, same note as E1's report).

## Report

Write your full report to
`.claude/plans/task-E2-report.md`. Run
`cd python && uv run pytest tests/test_investments_technologies.py
tests/test_investments_costs.py -v` (adjust filenames to what you
actually wrote) plus `uv run pytest -m "not slow"` for the full non-slow
suite, and `uv run pytest -m "not slow" -W error::UserWarning -q` to
confirm no new warnings. Reply with only DONE / DONE_WITH_CONCERNS /
NEEDS_CONTEXT / BLOCKED, the exact commands and pass counts, and a
one-line pointer to the report file — don't paste the report back.

State clearly in the report: which `tech`-class-inclusion reading you
used (the literal 9-class reading above, or a deviation and why), how you
handled the R39 "type present in document" check (full pipeline in the
test, or deferred to E6 — flag this explicitly either way since it
affects what E6 needs to pick up), and the exact capital-cost figures you
picked per class.

If anything here is ambiguous in a way that's load-bearing for later
tasks (E3-E6 build on this one), ask before guessing rather than after.