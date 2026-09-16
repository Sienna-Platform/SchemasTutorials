# Task JO6-9 — Finish the Julia operations tutorial (demand, sidecar,
# time series, combined driver)

This is a **prerequisite** discovered mid-session, not part of the
capacity-expansion plan's own numbered tasks. The capacity-expansion
plan (`.claude/plans/2026-09-01-capacity-expansion-example-plan.md`)
says its Julia tasks "mirror E1-E6 module-for-module against the Julia
operations tutorial, once that exists" — but the Julia operations
tutorial (`julia/RTSGMLCCase/`) is missing four modules the Python
operations tutorial (`python/src/rts_gmlc_case/`) already has:
`demand.py`, `sidecar.py`, `timeseries.py`, `build.py`. This task builds
their Julia equivalents so the investments mirror (a later, separate set
of tasks) has something complete to build on.

There is an existing design doc for exactly this gap:
`.claude/plans/2026-08-28-julia-rts-tutorial-plan.md`, Tasks 6-9 (read it
for Julia-specific API pointers — Parquet2 usage, the `SidecarWriter`
struct shape, `TimeZones`/`ZonedDateTime` idioms). **That doc is stale in
places where it conflicts with the Python code as actually built** — the
Python modules that now exist on disk are the ground truth for behavior
and exact values; the 2026-08-28 doc is only a secondary reference for
Julia mechanics. Two known, confirmed divergences (there may be others —
check every value, don't assume the old doc is otherwise reliable):

- **Resolution strings.** The old doc says `DAY_AHEAD -> "PT3600S"`,
  `REAL_TIME -> "PT300S"`. The actual Python `timeseries.py` (read it in
  full) uses **`"PT1H"`/`"PT5M"`** (its own docstring: *"R32 reverses the
  plan's `PT3600S`/`PT300S`"*). **Use `PT1H`/`PT5M`** — this is not
  optional, cross-language parity (a later task, JE7) depends on it.
- **`quantity_kind`.** The old doc says every association gets
  `quantity_kind = "active_power"`. The actual Python `timeseries.py` has
  a 5-entry `PARAMETER_TARGETS` map (`PMax MW`/`MW Load` ->
  `max_active_power`/`active_power`; `PMin MW` ->
  `min_active_power`/`active_power`; `Requirement` ->
  `requirement`/`active_power`; `Natural_Inflow` -> `inflow`/`power`) —
  **port this map exactly, not a single hardcoded value.**

Given these two confirmed divergences, treat **every** other value in
the old doc as similarly suspect — verify each one against the actual
Python source before porting it, rather than trusting the doc.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`python/`. Do not touch anything under
`julia/RTSGMLCCase/src/{data,document,topology,branches,generation}.jl`
except one small addition described below — this task is additive.

## Read these Python files in full before writing anything — they are
## the ground truth for behavior, field values, and mapping decisions

- `python/src/rts_gmlc_case/demand.py` — loads + reserves + service
  associations.
- `python/src/rts_gmlc_case/sidecar.py` — the parquet sidecar contract
  (content-addressed, atomic write, `data_hash` over `<f8`
  little-endian bytes, `timestamp` as `ms, UTC`).
- `python/src/rts_gmlc_case/timeseries.py` — the pointer-file reader
  (two CSV layouts, `PARAMETER_TARGETS`, owner resolution by `Category`,
  `resolve_case_insensitive_path`, the exact `SingleTimeSeries`/
  `TimeSeriesAssociation` field set).
- `python/src/rts_gmlc_case/build.py` — the combined driver and
  `read_case`.
- `python/build_rts.py` — the CLI shape (counts printed per type,
  parquet file count).

## Read these existing Julia files for idiom/API conventions before
## writing anything

- `julia/RTSGMLCCase/src/document.jl` — `PD = PowerOpenAPIModels` alias,
  `add!(doc, component) -> Int`, `PD.next_id!`, `PD.add_component!`,
  `PD.get_components`, `PD.validate_document`, `PD.write_document`,
  `PD.read_document`. There is **no Julia equivalent needed for
  `CaseDocument`** — `PowerOpenAPIModels.SystemDocument` already owns id
  minting and bucketing; don't build a Julia `CaseDocument` wrapper.
- `julia/RTSGMLCCase/src/topology.jl`, `branches.jl`, `generation.jl` —
  Julia style already established here: `function ... end` with
  explicit `return`, no ternaries, no `isa` gates, `iszero(x)`, errors
  named with the offending row/key, module-level `const` dicts for
  builder dispatch instead of `if`/`isa` chains, `CSV.read(path,
  DataFrame)` + `eachrow`.
- `julia/RTSGMLCCase/Project.toml` — already declares `Parquet2`,
  `TimeZones`, `JSON3`, `SHA` as deps (added in anticipation of this
  task) — no `Project.toml` edit should be needed. If you find a dep
  missing, say so in your report rather than silently adding one you
  aren't sure is right.
- `julia/RTSGMLCCase/src/generation.jl` has **no public unit-type ->
  target-component-type-name lookup** (it dispatches straight to builder
  functions via `GENERATOR_BUILDERS`, keyed by `Unit Type`, not to a
  type-name string). The time-series stage needs one (to resolve
  `owner_type` for `Category == "Generator"` pointer rows) — **add one
  small new public `const` to `generation.jl`** mirroring Python's
  `UNIT_TYPE_TO_MODEL` (12 entries — copy the Python dict's keys/values
  exactly, don't re-derive), e.g. `const UNIT_TYPE_TO_TARGET =
  Dict{String,String}(...)`. This is the one small addition to an
  existing file this task is allowed to make.

## New files

- `julia/RTSGMLCCase/src/demand.jl`
- `julia/RTSGMLCCase/src/sidecar.jl`
- `julia/RTSGMLCCase/src/timeseries.jl`
- `julia/RTSGMLCCase/src/build.jl`
- `julia/RTSGMLCCase/build_rts.jl` (CLI script, mirrors
  `python/build_rts.py`'s shape: takes an output dir argv, builds,
  prints component counts per type sorted, prints association counts,
  prints parquet file count)
- `julia/RTSGMLCCase/test/test_demand.jl`
- `julia/RTSGMLCCase/test/test_sidecar.jl`
- `julia/RTSGMLCCase/test/test_timeseries.jl`
- `julia/RTSGMLCCase/test/test_build.jl`
- Update `julia/RTSGMLCCase/src/RTSGMLCCase.jl` to `include` the four new
  source files (in an order that respects dependencies: `demand.jl`
  needs `topology.jl`; `timeseries.jl` needs `sidecar.jl`; `build.jl`
  needs everything).
- Update `julia/RTSGMLCCase/test/runtests.jl` to include the four new
  test files (read its current content first to match its existing
  pattern).
- Extend `julia/RTSGMLCCase/test/Project.toml` only if a new test-only
  dep is genuinely needed (check first; the main `Project.toml` already
  has the runtime deps).

## What to build (mirror the Python module's behavior exactly; the
## Python file is the spec, read it fully rather than relying on this
## summary)

### `demand.jl`

`add_loads!(doc, source::AbstractString, idx::TopologyIndex)` — one
`PowerLoad` per bus with nonzero `MW Load` (51 of 73). `add_reserves!(doc,
source, idx, gen_ids::Dict{String,Int}) -> Dict{String,Int}` — one
`OnlineReserve` per `reserves.csv` row (`time_frame` in minutes =
`Timeframe (sec) / 60`, `sustained_time = 60.0` fixed, not `3600.0`),
plus `PD.add_service_association!` rows for eligible generators (parse
`Eligible Device SubCategories`/`Eligible Regions`, both either a bare
value or a parenthesized comma list — port the Python parser's logic).
Check `PD.add_service_association!`'s actual signature in
`document.jl` (`function add_service_association!` around line 273) —
it may take an association model rather than two bare ints; match
whatever it actually expects, don't assume the Python argument order
without checking.

### `sidecar.jl`

`struct SidecarWriter` + constructor (creates `timeseries/` under
`case_dir`), `data_hash(values::Vector{Float64}) -> String` (SHA-256 hex
over the values as `<f8` little-endian bytes — Julia's native `Float64`
is already little-endian on essentially every real target, but verify
this rather than assume: use `htol.(values)` or equivalent explicit
little-endian conversion before reinterpreting to bytes, matching the
2026-08-28 doc's `reinterpret(UInt8, htol.(values))` approach, so the
hash is portable/correct regardless of host byte order — same reasoning
Python's docstring gives for forcing `<f8`), `write_series!(writer,
timestamps, values) -> (uri, data_hash)` — content-addressed
(`ts_<first-16-hex>.parquet`), atomic write (write to a temp path then
move into place — mirror Python's `os.replace` atomicity, Julia's `mv`
with `force=true` after writing to a uniquely-named temp file in the
same directory), re-write unconditionally rather than trusting
`isfile` as a validity proxy (same reasoning as the Python
`SidecarWriter`'s docstring). **Cross-language pin, critical:** a hash
computed here over `[1.0, 2.0, 3.0]` must equal what Python's
`rts_gmlc_case.sidecar.data_hash` produces for the same input — verify
this directly (`cd python && uv run python3 -c
"from rts_gmlc_case.sidecar import data_hash; import numpy as np;
print(data_hash(np.array([1.0,2.0,3.0])))"`), and assert the literal
value in a Julia test.

### `timeseries.jl`

`read_profile(csv_path, column::Union{String,Nothing}, resolution) ->
(timestamps, values)` dispatching on Layout A (has a `Period` column) vs
Layout B (no `Period` column, one row per day, `1..24`/`1..288` period
columns) — port both branches from Python's `_read_layout_a`/
`_read_layout_b`/`read_profile`. `resolve_case_insensitive_path(base,
relative) -> String` — **required**, not optional: RTS-GMLC's own
`timeseries_pointers.csv` disagrees with the source tree's real casing
in two places (`HYDRO` referenced vs `Hydro` on disk; one filename
casing mismatch under `Load/`) — this resolves silently on macOS
(case-insensitive filesystem) and would raise on Linux; port Python's
case-insensitive resolution logic so this Julia code is portable too,
not just macOS-working-by-accident. `attach_time_series!(doc, source,
sidecar, owners)` with an `Owners`/`TimeSeriesOwners`-equivalent struct
bundling `gen_ids`, `area_id_by_name`, `reserve_id_by_product` — for
each `timeseries_pointers.csv` row: resolve `resolution` via the
`PT1H`/`PT5M` map (see the divergence note above), resolve `target`
(`name`, `quantity_kind`) via the ported `PARAMETER_TARGETS`-equivalent
map, resolve owner by `Category` (`Generator` -> generator id via
`gen_uid`, resolving through `storage.csv`'s `Storage` -> `GEN UID`
column for the two `Natural_Inflow` rows whose `Object` is a storage
name, exactly as Python's `_resolve_generator_object` does; `Area`/
`Region`/`Zone` -> area id; `Reserve` -> reserve id), read the profile,
write it through `sidecar`, and attach one `SingleTimeSeries`/
`TimeSeriesAssociation` via `PD.add_time_series_association!` (check its
actual signature in `document.jl` around line 324). Field values (`
element_type`, `element_shape`, `units`, `unit_system`,
`time_reference`, etc.) exactly as Python's `attach_time_series` sets
them — port field-for-field, don't re-derive from the old 2026-08-19
doc's guesses about enum member names; check the actual generated
`SingleTimeSeries` struct's field types in
`InfrastructureTimeSeriesOpenAPIModels` (or wherever it's generated) for
the exact `element_type` enum member spelling for a 64-bit float.
`doc.time_series_storage_file` (or its Julia equivalent field/setter) is
set to `"timeseries"`.

### `build.jl` + `build_rts.jl`

`build_case(case_dir::AbstractString) -> SystemDocument` — every stage
in the fixed order (topology -> branches -> generation -> loads ->
reserves -> time series), matching Python's `build.py` stage order and
argument-threading exactly (`gen_ids` into `add_reserves!` and the
owners struct; `idx.area_id_by_name` into the owners struct), then
`PD.validate_document(doc)`, then `PD.write_document(doc,
joinpath(case_dir, "system.json"))`. `read_case(case_dir) ->
SystemDocument` = `PD.read_document` + `PD.validate_document`.
`build_rts.jl`: CLI script mirroring `python/build_rts.py`'s shape
exactly (argv = output dir; print `"wrote case to $case_dir"`; print
sorted per-type component counts; print association counts; print
parquet file count).

**Build the real case** into `julia/cases/rts-julia/` (a new directory —
check whether the Python side's `cases/` convention suggests this should
instead live at the repo-root `cases/rts-julia/` alongside
`cases/rts-python/`; use the repo-root location for consistency with the
Python side's existing `cases/rts-python/`, i.e.
`<repo-root>/cases/rts-julia/`, not a path nested under `julia/`) and
report the resulting component counts.

## Verify

- `julia --project=julia/RTSGMLCCase -e 'using RTSGMLCCase'` compiles
  clean after every file you add (check incrementally, not just at the
  end — this project's "verify each edit compiles before moving to the
  next" convention).
- `julia --project=julia/RTSGMLCCase/test julia/RTSGMLCCase/test/runtests.jl`
  passes in full (instantiate the test env first if needed:
  `julia --project=julia/RTSGMLCCase/test -e 'using Pkg; Pkg.instantiate()'`).
- The `data_hash([1.0, 2.0, 3.0])` cross-language literal check (above).
- Every association's `length` matches its source CSV's row count.
- Association counts match the Python build's counts (build both and
  compare, or at minimum compare against
  `python/tests/test_build.py`'s known pinned counts if any exist — read
  that test file to find them).
- `read_case` round-trips: build, read back, re-validate, compare
  component counts per bucket against the freshly-built `doc`.
- Byte-determinism: build twice into two temp dirs, compare
  `system.json` bytes.

Run JuliaFormatter over every file you touch if the project has a
formatter config (check for one, e.g. `.JuliaFormatter.toml` at the
workspace or package root) before finishing — this repo's global
instructions require running the project formatter before considering
Julia work complete.

## Report

Write your full report to
`.claude/plans/task-JO-report.md`. Reply with only DONE /
DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, the exact compile/test
commands you ran with pass counts, the component-count table from the
real `cases/rts-julia/` build, and a one-line pointer to the report
file.

State clearly in the report: every place you found the 2026-08-28 Julia
plan doc's text disagreeing with the actual current Python
implementation (not just the two divergences flagged above — list any
others you found), and the exact signatures you ended up using for
`PD.add_service_association!`/`PD.add_time_series_association!` (since
this brief guessed at them rather than confirming against
`document.jl`'s real source).

If anything here is ambiguous in a way that's load-bearing for the
later Julia investments-mirror tasks (which will extend these same
modules), ask before guessing rather than after.