# Task JE2 report — existing devices and supply technologies

## Status: DONE

## What was built

Ported `python/src/rts_gmlc_case/investments/technologies.py` and
`investments/costs.py` (the E2 slice only — capital-cost curve, financial
data, and `add_supply_technologies`; battery/transport helpers are JE3's
scope and were not added) into two new flat files under
`julia/RTSGMLCCase/src/`:

- `src/investments_costs.jl`
  - `CAPITAL_COST_PER_MW::Dict{String,Float64}` — the 9 class → USD/MW
    figures, copied verbatim from Python's `costs.py`.
  - `flat_linear_value_curve(proportional_term::Float64) -> PD.ValueCurve`
    — builds `PD.ValueCurve(PD.InputOutputCurve(; function_data =
    PD.InputOutputCurveFunctionData(PD.LinearFunctionData(; constant_term
    = 0.0, proportional_term))))`, confirmed directly against the
    generated model files in `PowerCoreOpenAPIModels.jl`/
    `InfrastructureCoreOpenAPIModels.jl`.
  - `capital_cost_curve(tech_class::AbstractString) -> PD.ValueCurve` —
    thin wrapper over `flat_linear_value_curve`, errors by name on an
    unknown class.
  - `financial_data_for(_tech_class::AbstractString) -> PD.TechnologyFinancialData`
    — `capital_recovery_period=25, technology_base_year=2030,
    debt_fraction=0.5, debt_rate=0.045, return_on_equity=0.11,
    tax_rate=0.21` (same numbers, same "illustrative ATB-adjacent, no
    live pull performed" framing as Python). Parameter is prefixed `_`
    (unused today) following the same convention JE1's
    `add_investment_topology!(doc, _source, idx)` already established in
    this codebase for an intentionally-unused signature parameter.

- `src/investments_technologies.jl`
  - `GENERATOR_DATABASE`, `POWER_SYSTEMS_TYPE_BY_CLASS` (9 classes →
    `"ThermalStandard"`/`"HydroDispatch"`/`"RenewableDispatch"`),
    `FUEL_NAME_BY_CLASS` (5 thermal classes → source `Fuel` name),
    ported verbatim from Python.
  - `add_supply_technologies!(doc, source, idx, inv_idx) -> Dict{String,Int}`
    — reads the ReEDS generator database, asserts `all(IsExistUnit)`
    (`error(...)` naming the file if violated), iterates
    `sort(collect(keys(POWER_SYSTEMS_TYPE_BY_CLASS)))` for determinism,
    errors by class name if a class has zero rows, builds one
    `PD.SupplyTechnology` (`region` = sorted zone ids via
    `inv_idx.zone_id_by_bus_number`, `fuel` = `[THERMAL_FUEL[...]]` for
    the 5 thermal classes else `nothing`, `capital_costs`/
    `financial_data` from the costs helpers above) plus one
    `PD.ExistingDevices` supplemental attribute (`existing_devices` =
    sorted `GEN UID` list) per class, and returns the class→id map.
  - `fuel` reuses the existing `THERMAL_FUEL` dict from `generation.jl`
    (no redefinition), with a `haskey` guard that errors by name if a
    fuel name were ever unmapped (mirrors the existing
    `_build_thermal_standard` pattern in `generation.jl`).
  - `prime_mover_type` is left at its field default (`nothing` is not
    set; the generated struct's own default is the plain string `"OT"`)
    — no workaround needed, confirmed the brief's note that Julia has no
    warning system to trip here.
  - Signature intentionally does not use `idx::TopologyIndex` (mirrors
    Python's `del idx  # unused`); parameter renamed `_idx` per this
    codebase's unused-parameter convention.

`src/RTSGMLCCase.jl` now includes, in order:
`investments_topology.jl` → `investments_costs.jl` →
`investments_technologies.jl` → `branches.jl` (costs before technologies
since the latter calls the former's functions at module load/compile
time via top-level function definitions — no forward-reference issue in
practice, but the order also matches "define before use" for readability).

New test files, both included into `test/runtests.jl` right after
`test_investments_topology.jl`:

- `test/test_investments_costs.jl` — 6 testsets covering: `CAPITAL_COST_PER_MW`
  covers exactly the 9 candidate classes; every cost is a plausible
  positive USD/MW figure; `capital_cost_curve`/`flat_linear_value_curve`
  produce the right `INPUT_OUTPUT`/`LINEAR`/zero-intercept shape (via a
  small `_linear_function_data` unwrap-and-assert helper, since Julia's
  `ValueCurve` is a nested `oneOf` rather than Python's flat pydantic
  dict); `financial_data_for` returns 9 distinct, fully-populated
  instances (checked via `objectid`, matching Python's `id(instance)`
  check); `capital_cost_curve` errors by name on an unknown class.
- `test/test_investments_technologies.jl` — 10 testsets mirroring
  Python's `tests/test_investments_technologies.py` one-for-one: row
  count/`IsExistUnit` sanity, exactly 9 `SupplyTechnology`s named by the
  9 classes with `distpv`/`csp-ns`/`battery_4` absent,
  `power_systems_type` matches the R39 table and the target type has
  ≥1 component in the same document (built via `add_topology!` +
  `add_generation!` first, same as Python's `_build` helper),
  `ExistingDevices` counts match a fresh CSV group-by (with the
  27/`gas-ct`, 19/`hydED`, 19/`o-g-s` pins from the brief),
  supplemental-attribute associations point at `SupplyTechnology`,
  `region` is non-empty/sorted/all-real-zone-ids, `fuel` is set only for
  the 5 thermal classes, `financial_data`/`capital_costs` are present on
  every technology, `PowerOpenAPIModels.validate_document(doc)` passes.
  Two additional testsets (no direct Python equivalent, added because
  the brief calls out both preconditions by name) build a temp copy of
  the generator-database CSV with one row's `IsExistUnit` flipped to
  `false`, and a second with all `upv` rows removed, and assert
  `add_supply_technologies!` raises an error naming `"IsExistUnit"` /
  `"upv"` respectively.

## Verification

- `julia --project=. -e 'using RTSGMLCCase'` — compiles clean (single
  successful precompile, no errors).
- Manual REPL smoke check (before writing test files) confirmed exact
  counts: 9 `SupplyTechnology`s, 9 `ExistingDevices` with sizes
  `[10, 27, 19, 16, 1, 19, 1, 25, 4]` for
  `[gas-cc, gas-ct, o-g-s, coalolduns, nuclear, hydED, hydEND, upv,
  wind-ons]`, `region` non-empty per class, `fuel` set only for the 5
  thermal classes, `validate_document(doc)` passes.
- `julia --project=test test/runtests.jl` — **4216 / 4216 tests pass**
  (baseline before this task was 3795; this task added 421 new
  assertions across the two new test files — confirmed by running just
  those two files standalone first: 421/421 pass in 11.8s).
- No `.JuliaFormatter.toml` exists anywhere under
  `SchemasTutorials/julia/` or at the repo root, so there is no
  configured formatter to run for this tutorial package (verified by
  `find`).

## Files touched

- `julia/RTSGMLCCase/src/investments_costs.jl` (new)
- `julia/RTSGMLCCase/src/investments_technologies.jl` (new)
- `julia/RTSGMLCCase/test/test_investments_costs.jl` (new)
- `julia/RTSGMLCCase/test/test_investments_technologies.jl` (new)
- `julia/RTSGMLCCase/src/RTSGMLCCase.jl` (added two `include`s)
- `julia/RTSGMLCCase/test/runtests.jl` (added two `include`s)

No other files were modified. `python/` was not touched.
`PowerOpenAPIModels` was read-only (model files inspected to confirm
field names/`ValueCurve` construction) and its checkout was not changed
(`main`, `0568d41`, verified via `git rev-parse`).

## Notes for JE3/JE5/JE6/JE7

- `add_supply_technologies!`'s return type is `Dict{String,Int}`
  (class name → `SupplyTechnology` id), same as the brief specifies.
- `flat_linear_value_curve` and `capital_cost_curve` live in
  `investments_costs.jl` and are unexported module-internal functions
  (called as `RTSGMLCCase.flat_linear_value_curve` etc. from outside, or
  bare from sibling files inside the module) — ready for JE3 to add
  `battery_capital_cost_curves`/`battery_operation_cost`/
  `transport_financial_data` to the same file.
- Nothing in this task's git working tree was staged, committed, or
  pushed, per the hard rule.
