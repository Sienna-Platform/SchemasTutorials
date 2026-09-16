# Task JE2 — Julia mirror of E2: existing devices and supply technologies

Mirrors `python/src/rts_gmlc_case/investments/technologies.py` and
`investments/costs.py` into Julia. Read both Python files in full — they
are ground truth. This task assumes **JE1 is already done and merged**
(`InvestmentTopologyIndex`, `add_investment_topology!` exist in
`julia/RTSGMLCCase/src/`) — if it isn't, report BLOCKED.

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `python/`. Do not change `PowerOpenAPIModels`'s git checkout
(stays on `main`, `0568d41`). Do not modify
`src/{data,document,topology,branches,generation}.jl` or the JE1 files
you're building on.

## The exact scenario, verbatim from Python — same 9 classes, same
## numbers, so the Julia and Python cases stay comparable

Read `task-E2-brief.md`/`task-E2-report.md`
(`.claude/plans/`) for the full worked reasoning if you want it, but the
concrete values to port are simply what's in
`investments/technologies.py`/`investments/costs.py` today:

- 9 `SupplyTechnology` candidates: `upv`, `wind-ons` (supply-curve
  classes), `gas-cc`/`gas-ct`/`o-g-s`/`coalolduns`/`nuclear` (thermal),
  `hydED`/`hydEND` (hydro). `distpv`/`csp-ns`/`battery_4` excluded.
- R39 `power_systems_type`: `"ThermalStandard"` (5 classes),
  `"HydroDispatch"` (2), `"RenewableDispatch"` (2).
- `fuel` set only for the 5 thermal classes (via the existing Julia
  `THERMAL_FUEL` dict in `generation.jl` — reuse it, same as Python
  reuses `generation.FUEL_BY_SOURCE`; don't redefine a fuel-name mapping).
- `ExistingDevices` supplemental attribute per class, `existing_devices`
  = sorted `GEN UID` list for that class from
  `capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv`.
- `region` = sorted zone ids the class's devices sit in (via JE1's
  `zone_id_by_bus_number`).
- Capital costs and financial data: **port the exact same numbers**
  Python's `costs.py` uses (`CAPITAL_COST_PER_MW` dict, the uniform
  `financial_data_for` values: `capital_recovery_period=25,
  technology_base_year=2030, debt_fraction=0.5, debt_rate=0.045,
  return_on_equity=0.11, tax_rate=0.21`) — same illustrative-provenance
  docstring framing, don't invent different numbers for the Julia side.

## Julia-specific construction notes (checked directly against the
## generated structs — use these, don't guess)

- **`ValueCurve` is a nested `oneOf` wrapper in Julia**, not a flat dict
  like Python's pydantic `RootModel`. A flat linear capital-cost curve is:

  ```julia
  PD.ValueCurve(
      PD.InputOutputCurve(;
          function_data = PD.InputOutputCurveFunctionData(
              PD.LinearFunctionData(; constant_term = 0.0, proportional_term = per_mw)
          ),
      ),
  )
  ```

  (Confirmed against `PowerCoreOpenAPIModels.jl/src/models/model_ValueCurve.jl`,
  `model_InputOutputCurve.jl`, `model_InputOutputCurveFunctionData.jl`,
  `model_LinearFunctionData.jl`.) Write one small helper,
  `flat_linear_value_curve(per_unit::Float64) -> PD.ValueCurve`, mirroring
  Python's `costs.py`'s `capital_cost_curve`/`flat_linear_value_curve`
  helper (E3 generalized Python's into a reusable one — do the same here
  from the start, since this task and JE3 both need it).
- **No `prime_mover_type`-enum-default bug in Julia.** Python's E2 had to
  work around a pydantic serializer warning from
  `SupplyTechnology.prime_mover_type`'s buggy `"OT"` string default (not
  the enum). Julia's generated `SupplyTechnology.prime_mover_type` is a
  plain `Union{Nothing,String} = "OT"` — a plain string default with no
  warning system to trip. **You do not need to set `prime_mover_type`
  explicitly at all** unless you want to for clarity; there's no Julia
  equivalent of Python's `-W error::UserWarning` gate to satisfy here.
- `TechnologyFinancialData`, `ExistingDevices`, `SupplyTechnology` structs
  live in `PowerInvestmentsOpenAPIModels` (already a Project.toml dep, no
  edit needed) — check each struct's exact keyword field names in
  `PowerOpenAPIModels/PowerInvestmentsOpenAPIModels.jl/src/models/model_*.jl`
  before writing constructor calls; don't assume field names/order match
  Python's pydantic field names one-to-one without checking (they should
  match in name, per the shared OpenAPI schema, but verify).
- Supplemental attribute: `attribute.id = PD.next_id!(doc)` then
  `PD.add_supplemental_attribute!(doc, attribute, component_id)` — no
  `component_type` argument needed (same as JE1).

## New files (flat under `src/`, matching this package's existing
## layout — no `src/investments/` subdirectory)

- `julia/RTSGMLCCase/src/investments_technologies.jl`
- `julia/RTSGMLCCase/src/investments_costs.jl`
- `julia/RTSGMLCCase/test/test_investments_technologies.jl`
- `julia/RTSGMLCCase/test/test_investments_costs.jl`
- Update `RTSGMLCCase.jl` (`include` in order after JE1's file) and
  `test/runtests.jl`.

## What to build

`add_supply_technologies!(doc, source::AbstractString, idx::TopologyIndex,
inv_idx::InvestmentTopologyIndex) -> Dict{String,Int}` (class name -> id)
— port Python's `add_supply_technologies` logic exactly (sorted
class-name iteration, `IsExistUnit` all-true precondition check, empty-
class check, both raising `error(...)` naming the offending value — this
project's "never extend a silent-failure pattern" convention).

`flat_linear_value_curve`, `capital_cost_curve(tech_class) ->
PD.ValueCurve`, `financial_data_for(tech_class) ->
PD.TechnologyFinancialData` in `investments_costs.jl`.

## Verify (port Python's test assertions)

- 9 `SupplyTechnology` components, exact class set, `distpv`/`csp-ns`/
  `battery_4` absent.
- `power_systems_type` per class matches the table above.
- `ExistingDevices` counts match a fresh CSV group-by (27 for `gas-ct`,
  19 for `hydED`/`o-g-s`, etc.).
- `region` non-empty, sorted, every id a real zone id.
- `financial_data`/`capital_costs` present on every one.
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean.
- `julia --project=test test/runtests.jl` passes in full (no
  regression on the now-3659-test baseline).

## Report

Write your full report to `.claude/plans/task-JE2-report.md`. Reply with
only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, compile/test
commands and pass counts, and a one-line pointer to the report file.

If anything here is ambiguous in a way that's load-bearing for JE3/JE5/
JE6/JE7 (which build on this task's return value), ask before guessing.