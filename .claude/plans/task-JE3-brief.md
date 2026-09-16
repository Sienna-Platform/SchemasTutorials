# Task JE3 — Julia mirror of E3: storage and transport technologies

Mirrors `python/src/rts_gmlc_case/investments/storage.py` and
`investments/transport.py` into Julia. Read both in full — ground truth.
Assumes **JE1 and JE2 are already done and merged**. If either isn't,
report BLOCKED.

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `python/`. Do not change `PowerOpenAPIModels`'s checkout. Do
not modify `src/{data,document,topology,branches,generation}.jl` or the
JE1/JE2 files.

## Part A — `StorageTechnology` (1 candidate, `battery_4`)

Same single-row source data Python used (`GEN UID` `"313_STORAGE_1"`,
`Bus ID` 313, `cap` 50.0 MW, `Storage Roundtrip Efficiency` 85). Port
`storage.py` exactly:

- `power_systems_type = "EnergyReservoirStorage"` (R39's 4th string).
- `storage_tech = "OTHER_CHEM"` — this field is a plain
  `Union{Nothing,String}` in the generated Julia struct (confirmed), not
  an enum type — just pass the string literal, same as Python's
  `StorageTech.OTHER_CHEM` resolves to.
- `efficiency`: reuse the exact formula `generation.jl`'s
  `_build_energy_reservoir_storage` already uses for the operations side
  (`sqrt(Storage Roundtrip Efficiency / 100.0)`, split evenly across
  in/out) — same convention, same source column.
  **Verify field-name syntax before using it:** `InOut`'s generated
  struct has fields literally named `in`/`out`
  (`PowerInOut... in::Union{Nothing,Float64}`, `out::...`) — `in` is a
  Julia reserved word. Check whether `PD.InOut(; in = leg, out = leg)`
  compiles as-is, or whether it needs `PD.InOut(; var"in" = leg, out =
  leg)` (Julia's escaped-identifier syntax for a keyword used as a name).
  Test this directly in the REPL before writing it into source, and note
  which form worked in your report — the existing operations-side
  `generation.jl` already constructs `PD.InOut(...)` somewhere for the
  same field on `EnergyReservoirStorage`, so check exactly how it spells
  that call and copy it verbatim rather than re-deriving.
- `capacity_limits_charge`/`capacity_limits_discharge` = `MinMax(min=0.0,
  max=50.0)` (the dataset-backed `cap` value); `capacity_limits_energy =
  nothing` (no MWh figure in the dataset — don't invent one).
  `duration_limits = nothing` (both duration CSVs are header-only, zero
  data rows — verify this directly, same as Python did, with a test).
- `capital_costs_energy`/`_charge`/`_discharge`,
  `financial_data`: **port the exact same illustrative figures** E3's
  Python `costs.py` extension uses (`$200,000/MW` charge/discharge,
  `$300,000/MWh` energy) via JE2's `flat_linear_value_curve` helper.
  `operation_costs`: an all-zero `StorageCost` (check its exact Julia
  field names before constructing).
- One `ExistingDevices` supplemental attribute
  (`existing_devices = ["313_STORAGE_1"]`), same mechanism as JE1/JE2.

`add_storage_technologies!(doc, source, inv_idx) -> Dict{String,Int}`.

## Part B — Transport technologies

Port `transport.py` exactly, **including its load-bearing duplicate-pair
ruling** (already recorded in the progress ledger,
`.claude/plans/2026-09-01-capacity-expansion-progress.md` — read it):
`transmission_capacity_init_AC_rts_nodal.csv` has 120 rows but 108
distinct `(From_Bus, To_Bus)` pairs (12 duplicated, identical
`MW_f0`/`MW_r0`, no circuit-id column). **Build exactly 108
`NodalACTransportTechnology` components, summing `MW_f0` across
duplicate rows per pair** — this exact count and rule must match the
Python side; a different count here breaks JE7 (the eventual
cross-language equivalence check for the combined case).

- `power_systems_type`: `"Line"` (AC) / `"TwoTerminalGenericHVDCLine"`
  (HVDC) — matching what the Julia operations `branches.jl` actually
  builds for the analogous devices (confirmed on the Python side against
  `rts_gmlc_case.branches`; do the equivalent check against
  `julia/RTSGMLCCase/src/branches.jl` here, don't assume the string is
  identical without checking — it should be, same schema, but verify).
- `capital_costs`: genuinely dataset-sourced (not illustrative) —
  `USD2004perMW` from the cost files, via `flat_linear_value_curve`. No
  inflation adjustment (same documented limitation as Python).
- `financial_data.capital_recovery_period = 40` (genuinely sourced from
  `scalars.csv`'s `trans_crp` row) — the other 5 fields illustrative,
  same values as elsewhere. Add a `transport_financial_data()` helper to
  `investments_costs.jl` (JE2's file), mirroring Python's.
- HVDC: 1 component from the single matching row pair (`b113`/`b316`,
  100 MW, 70 miles, `USD2004perMW` 644267.96).
- `resistance`/`reactance`/`voltage`/`unit_size`/`line_loss`: left at
  schema defaults, no dataset backing.

`add_transport_technologies!(doc, source, inv_idx) -> (ac_id_by_bus_pair,
hvdc_id_by_bus_pair)` (`Dict{Tuple{Int,Int},Int}` each).

## New files (flat under `src/`)

- `julia/RTSGMLCCase/src/investments_storage.jl`
- `julia/RTSGMLCCase/src/investments_transport.jl`
- `julia/RTSGMLCCase/test/test_investments_storage.jl`
- `julia/RTSGMLCCase/test/test_investments_transport.jl`
- Extend `julia/RTSGMLCCase/src/investments_costs.jl` (JE2's file) with
  the battery cost helpers + `transport_financial_data()`.
- Update `RTSGMLCCase.jl` and `test/runtests.jl` includes.

## Verify

- 1 `StorageTechnology`, `power_systems_type ==
  "EnergyReservoirStorage"`, 1 matching `ExistingDevices`.
- `duration_limits === nothing`, both duration CSVs confirmed
  zero-data-row.
- **Exactly 108** `NodalACTransportTechnology` (assert against a fresh
  CSV group-by, not a hardcoded literal — but the literal `108` should
  also appear as an explicit sanity pin).
- 1 `NodalHVDCTransportTechnology`, `capacity_limits.max == 100.0`.
- Every transport `financial_data.capital_recovery_period == 40`.
- Every AC/HVDC `start_node`/`end_node` resolves to a real Node id.
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean.
- `julia --project=test test/runtests.jl` passes in full, no regression.

## Report

Write your full report to `.claude/plans/task-JE3-report.md`. Reply with
only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, compile/test
commands and pass counts, and a one-line pointer to the report file.
State clearly which `InOut` construction syntax worked
(`in=`/`var"in"=`).

If anything here is ambiguous in a way that's load-bearing for JE5/JE6/
JE7, ask before guessing.