# Task JE3 report — Julia mirror of E3: storage and transport technologies

## Status: complete

## What was read (ground truth)

- `python/src/rts_gmlc_case/investments/storage.py` and `investments/transport.py` in full.
- `python/src/rts_gmlc_case/investments/costs.py` (the E3 additions: `battery_capital_cost_curves`,
  `battery_operation_cost`, `transport_financial_data`).
- `python/tests/test_investments_storage.py` and `test_investments_transport.py` (ported every
  assertion into the Julia test files below).
- `.claude/plans/2026-09-01-capacity-expansion-progress.md` (confirmed JE1/JE2 done, the
  duplicate-pair ruling, and the `PowerOpenAPIModels` branch history).
- Julia JE1/JE2 files for convention: `investments_topology.jl`, `investments_technologies.jl`,
  `investments_costs.jl`, `document.jl` (`add!`, `PD.next_id!`, `PD.add_supplemental_attribute!`),
  `generation.jl` (`_build_energy_reservoir_storage` — the exact efficiency formula and `InOut`
  call site to copy), `branches.jl` (confirmed `PD.Line` / `PD.TwoTerminalGenericHVDCLine`).
- Generated struct sources directly in `/Users/jdlara/cache/psy6/PowerOpenAPIModels` (checked out
  on `main` at `0568d41`, untouched): `StorageTechnology`, `InOut`, `StorageCost`,
  `StorageCostStartUp`, `MinMax`, `ExistingDevices`, `NodalACTransportTechnology`,
  `NodalHVDCTransportTechnology`.
- Source CSVs directly: `data/RTS-investments/capacitydata/...` (battery row), both
  `storagedata/*.csv` (confirmed header-only), both `transmission/transmission_capacity_init_*`
  and `transmission_distance_cost_*` files (confirmed 120 rows / 108 unique pairs / 12 exact
  duplicates, and the single HVDC row `b113,b316,100`).

## InOut construction syntax — confirmed

`PD.InOut(; in = leg_efficiency, out = leg_efficiency)` compiles and works as-is — verified both
directly in the REPL (`PD.InOut(; in = 0.5, out = 0.5)` → succeeds) and by finding
`generation.jl`'s existing `_build_energy_reservoir_storage` already uses this exact form. No
`var"in"` escaping needed. Copied the call verbatim into `investments_storage.jl`.

## Files added

- `julia/RTSGMLCCase/src/investments_storage.jl` — `BATTERY_TECH_CLASS = "battery_4"`,
  `add_storage_technologies!(doc, source, inv_idx) -> Dict{String,Int}`.
- `julia/RTSGMLCCase/src/investments_transport.jl` — `AC_CAPACITY_FILE`/`AC_COST_FILE`/
  `HVDC_CAPACITY_FILE`/`HVDC_COST_FILE`, `_bus_number`, `_add_ac_transport_technologies!`,
  `_add_hvdc_transport_technologies!`, `add_transport_technologies!(doc, source, inv_idx) ->
  (ac_id_by_bus_pair, hvdc_id_by_bus_pair)`.
- `julia/RTSGMLCCase/test/test_investments_storage.jl` — 13 testsets, ports every Python
  assertion in `test_investments_storage.py` (skipped only the Python-specific "no warnings /
  pydantic UserWarning" test, which has no Julia analogue — this OpenAPI generator has no
  serializer-warning behavior to avoid).
- `julia/RTSGMLCCase/test/test_investments_transport.jl` — 12 testsets, ports every Python
  assertion in `test_investments_transport.py` (same omission: no warnings test).

## Files extended

- `julia/RTSGMLCCase/src/investments_costs.jl` (JE2's file) — added
  `BATTERY_CAPITAL_COST_PER_MW_CHARGE`/`_DISCHARGE`/`_MWH_ENERGY` (200_000 / 200_000 / 300_000,
  same as Python), `battery_capital_cost_curves()`, `battery_operation_cost()` (all-zero
  `StorageCost`, `start_up = PD.StorageCostStartUp(0.0)` matching `generation.jl`'s
  `_storage_operation_cost` pattern), `transport_financial_data()`
  (`capital_recovery_period = 40`, other 5 fields identical to `financial_data_for`).
- `julia/RTSGMLCCase/src/RTSGMLCCase.jl` — added the two new `include`s after
  `investments_technologies.jl`, before `branches.jl`.
- `julia/RTSGMLCCase/test/runtests.jl` — added the two new test `include`s after
  `test_investments_technologies.jl`, before `test_branches.jl`.

No other files touched. `src/{data,document,topology,branches,generation}.jl` and the JE1/JE2
files were read but not modified. `python/` untouched. `PowerOpenAPIModels` checkout untouched
(confirmed `main` @ `0568d41` before and after).

## Design decisions / things worth flagging

- **`prime_mover_type` not in the brief's bullet list but ported anyway.** Python's
  `storage.py` explicitly sets `prime_mover_type=PrimeMovers.BA` (not just to dodge a pydantic
  warning — its own docstring says "this candidate always models a battery, so BA is not just
  warning-avoidance — it is the correct value"). The brief's Part A bullets don't mention this
  field, but the header line says "port storage.py exactly," so I set
  `prime_mover_type = "BA"` in the Julia struct too (default would otherwise be `"OT"`). This
  is a straight mechanical port of a value Python treats as semantically correct, not a new
  design choice — flagging it since it wasn't spelled out in the brief's checklist, in case it's
  considered out of scope for JE3 and belongs to a later stage instead. Verified: no downstream
  test in JE1/JE2/JE3 depends on this field's value, so it shouldn't be load-bearing for JE5/6/7.
- **Duplicate-pair AC summing** implemented with `combine(groupby(capacity, ["From_Bus",
  "To_Bus"]), "MW_f0" => sum => "MW_f0")`, matching Python's `groupby(...).sum()`. Verified
  against the exact numbers the brief and Python tests pin: `AC_115_121` → 1000.0 (sum of two
  500.0 rows), `AC_101_102` → 175.0 (single row, unchanged). Confirmed 108 unique pairs / 12
  duplicated pairs directly against a fresh CSV read (both in the test and in a REPL smoke run).
- **Python's "no warnings" tests were not ported** — they exercise a pydantic-specific
  serializer-warning quirk in the Python OpenAPI codegen that has no Julia equivalent (Julia's
  generated structs have no serializer warning mechanism). Everything else in both Python test
  files was ported.

## Verification performed

- `julia --project=. -e 'using RTSGMLCCase'` → compiles clean (no warnings, no errors).
- Interactive REPL smoke run of the full stage sequence (topology → generation → investment
  topology → supply technologies → storage → transport) before writing any test file, confirming
  live values: 1 `StorageTechnology` (`power_systems_type = "EnergyReservoirStorage"`,
  `efficiency = {in: 0.9219544457292888, out: 0.9219544457292888}` = `sqrt(0.85)`,
  `capacity_limits_charge/discharge = {min: 0.0, max: 50.0}`, `capacity_limits_energy = nothing`,
  `duration_limits = nothing`, `storage_tech = "OTHER_CHEM"`, `prime_mover_type = "BA"`), 108 AC
  transport technologies, 1 HVDC transport technology (`capacity_limits.max = 100.0`), and
  `PD.validate_document(doc)` passed with no error.
- Ran the two new test files in isolation first (`test_investments_storage.jl` +
  `test_investments_transport.jl` under a minimal `@testset`): **1067/1067 passed**.
- Ran the full suite: `julia --project=test test/runtests.jl` → **5283/5283 passed**, exit code
  0, ~4m03s wall time. No regressions (every prior JE1/JE2/JO/operations test still green).
- No JuliaFormatter config exists anywhere in this repo (confirmed by search, consistent with
  JE1/JE2's prior finding) — hand-formatted the new files to match the existing 4-space-indent,
  spaces-around-operators style already used in `topology.jl`/`investments_technologies.jl`.

## Verify checklist from the brief — all confirmed

- 1 `StorageTechnology`, `power_systems_type == "EnergyReservoirStorage"`, 1 matching
  `ExistingDevices` (`existing_devices == ["313_STORAGE_1"]`). ✓
- `duration_limits === nothing`; both duration CSVs confirmed zero-data-row directly (both by a
  standalone CSV read and via the test). ✓
- Exactly 108 `NodalACTransportTechnology`, asserted against a fresh CSV group-by (not just the
  hardcoded literal) and the literal `108` also pinned explicitly. ✓
- 1 `NodalHVDCTransportTechnology`, `capacity_limits.max == 100.0`. ✓
- Every transport `financial_data.capital_recovery_period == 40` (AC and HVDC). ✓
- Every AC/HVDC `start_node`/`end_node` resolves to a real `Node` id. ✓
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean. ✓
- `julia --project=test test/runtests.jl` passes in full, no regression (5283/5283). ✓

## Commands run

- `julia --project=. -e 'using RTSGMLCCase'` → compiled clean.
- `julia --project=test test/runtests.jl` → 5283/5283 passed (~4m03s).
