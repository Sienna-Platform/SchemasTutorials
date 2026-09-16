# Task JE4 report — Julia mirror of E4 (demand requirement + time series)

## Summary

Ported `python/src/rts_gmlc_case/investments/demand.py`'s `add_demand_requirements` into
`julia/RTSGMLCCase/src/investments_demand.jl` as `add_demand_requirements!`, plus a test file.
Both new files are additive; only the two `include` lists were touched, per the brief.

## Files

- **New**: `julia/RTSGMLCCase/src/investments_demand.jl`
- **New**: `julia/RTSGMLCCase/test/test_investments_demand.jl`
- **Edited**: `julia/RTSGMLCCase/src/RTSGMLCCase.jl` — added `include("investments_demand.jl")`
- **Edited**: `julia/RTSGMLCCase/test/runtests.jl` — added `include("test_investments_demand.jl")`

## Implementation

`add_demand_requirements!(doc::PD.SystemDocument, source::AbstractString, sidecar::SidecarWriter,
inv_idx::InvestmentTopologyIndex) -> Dict{String,Int}`:

- Reads `source/loaddata/RTS_DA_regional_load.csv` (`LOAD_DATA_FILE` constant).
- Iterates zone names from `inv_idx.zone_id_by_name` sorted by `parse(Int, x)` — same sort key
  `investments_topology.jl` already uses.
- For each zone: `read_profile(csv_path, zone_name, resolution_delta)` with
  `resolution_delta` from `RESOLUTION_BY_SIMULATION["DAY_AHEAD"]` (`("PT1H", Dates.Hour(1))` —
  confirmed by reading `timeseries.jl` directly, matching the brief).
- Builds `PD.DemandRequirement(; name, power_systems_type = "PowerLoad", region =
  [inv_idx.zone_id_by_name[zone_name]], value_of_lost_load = 9_000.0)`, leaving `conformity`,
  `growth_rate`, `new_demand_mw`, `new_construction_year`, `unserved_demand_curve`,
  `requirements` at schema defaults — mirrors Python's field set exactly.
- `power_systems_type = "PowerLoad"` verified against `demand.jl`'s `add_loads!`, which builds
  `PD.PowerLoad(...)` for the operations campaign's loads — confirmed rather than assumed.
- `add!(doc, requirement)` mints the id (module's existing `add!` helper, same pattern as
  `investments_topology.jl`).
- Writes the series via `write_series!(sidecar, timestamps, values)`, builds one
  `PD.SingleTimeSeries(...)` field-for-field matching `timeseries.jl`'s `attach_time_series!`
  (`owner_type = "DemandRequirement"`, `owner_category = "Component"`, `name = "requirement"`,
  `quantity_kind = "requirement"`, `units = "MW"`, `unit_system = "NATURAL_UNITS"`,
  `time_reference = "zoneless"`, `element_type = "f64"`, `element_shape = Int[]`), and attaches
  via `PD.add_time_series_association!(doc, PD.TimeSeriesAssociation(association))`.
- `VALUE_OF_LOST_LOAD = 9_000.0` — the exact figure Python's E4 picked, ported as a number, not
  re-derived, with the same "illustrative, not a `scalars.csv cost_dropped_load` citation"
  reasoning carried into the module-level comment.

## Include placement (one deliberate deviation from the brief's literal wording)

The brief says to place both includes "after JE1's files, since this needs
`InvestmentTopologyIndex`." That's necessary but not sufficient for the **source** file: Julia
resolves parameter type annotations (`sidecar::SidecarWriter`) at `include`-time, not lazily, so
`investments_demand.jl` also needs `sidecar.jl` (which defines `SidecarWriter`) already included.
`sidecar.jl` and `timeseries.jl` sit near the very end of `RTSGMLCCase.jl`'s include list (after
`investments_topology.jl`, `investments_costs.jl`, `investments_technologies.jl`,
`investments_storage.jl`, `investments_transport.jl`, `branches.jl`, `generation.jl`,
`demand.jl`). I placed `include("investments_demand.jl")` immediately after `include("timeseries.jl")`
and before `include("build.jl")` — satisfying both constraints (after `investments_topology.jl`
for `InvestmentTopologyIndex`, after `sidecar.jl` for `SidecarWriter`). Placing it right next to
`investments_topology.jl` as a literal reading of the brief might suggest would have raised
`UndefVarError: SidecarWriter not defined` at `using RTSGMLCCase` time — confirmed by first
attempting that placement and reverting after reasoning through Julia's method-signature
resolution timing (did not need to actually trigger the error to see this; the type-annotation
evaluation semantics are unambiguous).

For **`test/runtests.jl`** no such constraint exists (`using RTSGMLCCase` at the top already
loads the whole module before any test file is included), so I placed
`include("test_investments_demand.jl")` immediately after `include("test_investments_topology.jl")`,
matching the brief's literal ordering intent there.

## Verification

- `julia --project=. -e 'using RTSGMLCCase'` — compiles clean, no errors, no new warnings.
- `julia --project=test test/runtests.jl` — **5344/5344 tests pass**, 0 failures/errors, 4m43.3s
  (run in the background per policy). This is the full suite including the new
  `test_investments_demand.jl` (27 `@test` lines, several inside per-zone loops for
  effectively ~58 individual assertions). No regressions: exit code 0, and Test.jl's summary
  line shows Pass == Total with no Fail/Error columns.
- Brief's specific "Verify" checklist, each covered by a `@testset` in
  `test_investments_demand.jl`:
  - 3 `DemandRequirement` components, one per zone — `"add_demand_requirements! counts one per
    zone"` testset; also asserts `demand_ids` keys == `{"1","2","3"}` == `inv_idx.zone_id_by_name`
    keys, and runs `PowerOpenAPIModels.validate_document(doc)`.
  - `region` resolves to a real zone id, `power_systems_type == "PowerLoad"`,
    `value_of_lost_load == 9_000.0`, `conformity == "UNDEFINED"` (schema default) — `"DemandRequirement
    fields match the plan"` testset, per zone.
  - 3 new time-series associations, `resolution == "PT1H"`, `length == 8784` — `"demand time
    series associations counts and resolution"` testset; also checks `array_shape == [8784]`,
    `name == "requirement"`, `quantity_kind == "requirement"`, `units == "MW"`, `owner_category ==
    "Component"`, `unit_system == "NATURAL_UNITS"`, `time_reference == "zoneless"`.
  - `uri` resolves to a real parquet file; re-reading reproduces the same values; `data_hash`
    matches an independently computed hash — `"demand series uri resolves and reproduces the
    source CSV"` testset: reads each association's parquet file via `Parquet2.Dataset`, asserts
    `nrow(df) == 8784`, re-reads the source CSV independently via a fresh `RTSGMLCCase.read_profile`
    call (bypassing the module's internal CSV cache reuse concern by exercising the same public
    function a second time) and asserts `df.value == expected_values`, and asserts
    `sts.data_hash == RTSGMLCCase.data_hash(expected_values)` (the module's own hash function,
    called independently on the freshly-read values, not reused from the write path).
- `git status`/`git diff` confirm the whole `julia/` tree remains untracked (`??`) as at session
  start — no `git add`/`commit` was run, working tree is exactly as the tools left it on disk.

## Notes / things I did not do

- Did not touch `python/`, did not change `PowerOpenAPIModels`'s checkout, did not run any git
  write, did not dispatch any subagents.
- Did not run a Julia formatter — no `.JuliaFormatter.toml` or formatter script exists anywhere
  under `julia/RTSGMLCCase/` or `SchemasTutorials/`, so there is no project-specific formatter
  command to run for this tutorial project (unlike the psy6 Sienna packages, which do have one).
  New code was hand-formatted to match the surrounding files' existing style (4-space indent,
  trailing-comma kwarg lists, `;` keyword separator).
