# Task JE4 — Julia mirror of E4: demand requirement and its time series

Mirrors `python/src/rts_gmlc_case/investments/demand.py` into Julia.
Read it in full — ground truth. Assumes **JE1 is done and merged**
(only dependency — JE2/JE3 aren't needed for this task). If JE1 isn't
merged, report BLOCKED.

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `python/`. Do not change `PowerOpenAPIModels`'s checkout. Do
not modify any existing file except the two `include` list appends
(`RTSGMLCCase.jl`, `test/runtests.jl`).

## Reuse the Julia operations `timeseries.jl` directly — everything you
## need is already public

- `RESOLUTION_BY_SIMULATION["DAY_AHEAD"]` -> `("PT1H",
  Dates.Hour(1))`-shaped tuple (check the exact `Dates.Period` type
  used, e.g. `Dates.Hour(1)` vs `Dates.Minute(60)` — match whatever
  `timeseries.jl` itself already uses for `DAY_AHEAD`).
- `read_profile(csv_path::AbstractString, column::Union{AbstractString,
  Nothing}, resolution::Dates.Period) ->
  (timestamps::Vector{ZonedDateTime}, values::Vector{Float64})` — Layout
  A dispatch works unmodified for this task's CSV (see below).
- `write_series!(sidecar::SidecarWriter, timestamps, values) -> (uri,
  data_hash)` from `sidecar.jl`.
- `PD.SingleTimeSeries(; ...)` + `PD.add_time_series_association!(doc,
  PD.TimeSeriesAssociation(single_time_series))` — copy the exact
  field-construction pattern `timeseries.jl`'s `attach_time_series!`
  already uses (read it, lines ~272-296) rather than re-deriving field
  names.

## Data

`data/RTS-investments/loaddata/RTS_DA_regional_load.csv` (under
`investments_source_dir()`): `Year,Month,Day,Period,1,2,3` — Layout A,
8784 data rows, columns `"1"`/`"2"`/`"3"` matching JE1's zone names
exactly.

## What to build

`add_demand_requirements!(doc, source::AbstractString,
sidecar::SidecarWriter, inv_idx::InvestmentTopologyIndex) ->
Dict{String,Int}` — port `demand.py`'s `add_demand_requirements` exactly:

- For each zone name in sorted (`by = x -> parse(Int, x)`) order:
  - `timestamps, values = read_profile(csv_path, zone_name,
    resolution_delta)` where `resolution_delta` is `DAY_AHEAD`'s
    `Dates.Period` from `RESOLUTION_BY_SIMULATION`.
  - Build one `PD.DemandRequirement`: `power_systems_type =
    "PowerLoad"` (confirmed against the Julia operations `demand.jl` —
    check it builds `PD.PowerLoad`, same as Python's `demand.py` does —
    don't assume, verify), `region = [inv_idx.zone_id_by_name[zone_name]]`,
    `conformity` left at schema default, `value_of_lost_load = 9_000.0`
    (**the exact same illustrative figure Python's E4 picked** — port
    the number, not just the idea, so the two cases stay comparable;
    it's labeled illustrative/unsourced in both languages, same
    reasoning: not a citation of `scalars.csv`'s similarly-sized
    `cost_dropped_load` figure, which is explicitly restricted to
    historical years).
  - `add!(doc, requirement)`.
  - Write the series via `write_series!(sidecar, timestamps, values)`,
    build one `PD.SingleTimeSeries` (`owner_type = "DemandRequirement"`,
    `name = "requirement"`, `quantity_kind = "requirement"`, everything
    else matching the pattern in `timeseries.jl`'s existing usage), and
    attach via `PD.add_time_series_association!(doc,
    PD.TimeSeriesAssociation(association))`.
- Return `Dict{String,Int}` (zone name -> minted id).

## New files (flat under `src/`)

- `julia/RTSGMLCCase/src/investments_demand.jl`
- `julia/RTSGMLCCase/test/test_investments_demand.jl`
- Update `RTSGMLCCase.jl`/`test/runtests.jl` includes (after JE1's
  files, since this needs `InvestmentTopologyIndex`).

## Verify

- 3 `DemandRequirement` components, one per zone, `region` resolving to
  a real zone id.
- 3 new `time_series_associations`, `resolution == "PT1H"`, `length ==
  8784` (assert against a fresh CSV read).
- `uri` resolves to a real parquet file; re-reading it reproduces the
  same values; `data_hash` matches an independently computed hash of
  the same values.
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean.
- `julia --project=test test/runtests.jl` passes in full, no
  regression on the current baseline (check the current count before
  you start — it was 3795 after JE1; it may be higher if JE2/JE3 have
  landed by the time you run, in which case use whatever the baseline
  is right before your own changes).

## Report

Write your full report to `.claude/plans/task-JE4-report.md`. Reply
with only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED,
compile/test commands and pass counts, and a one-line pointer to the
report file.

If anything here is ambiguous in a way that's load-bearing for JE6/JE7,
ask before guessing.