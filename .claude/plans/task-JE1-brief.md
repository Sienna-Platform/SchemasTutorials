# Task JE1 — Julia mirror of E1: investments topology (Node/Zone/TopologyMapping)

Mirrors Python's `python/src/rts_gmlc_case/investments/topology.py` and
`investments/data.py` into Julia, module-for-module, into
`julia/RTSGMLCCase/`. Read both Python files in full — they are the
ground truth for behavior and values, not something to re-derive.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`python/`. This task assumes the Julia operations tutorial is complete
(topology/branches/generation/demand/sidecar/timeseries/build all exist
and pass tests) — if `julia/RTSGMLCCase/src/demand.jl` or
`timeseries.jl` don't exist yet when you start, STOP and report BLOCKED;
don't try to build them yourself, that's separate prerequisite work that
should already be done before this task starts.

## Environment note

`PowerOpenAPIModels` (the sibling schema-package repo, a path dependency)
is now on branch `main` (commit `0568d41`), switched there by the
controller earlier this session to fix an incompatible-branch blocker.
`RTSGMLCCase`'s `Manifest.toml`/`test/Manifest.toml` were freshly
regenerated against it and are known-good (3659/3659 tests passing as of
the last task). Do not change `PowerOpenAPIModels`'s checkout. If you hit
any resolve/compile issue, verify it's not something you introduced
before assuming another environment problem — the baseline is currently
clean.

## Julia API differences from Python you need (read the existing Julia
## code before writing anything)

- `julia/RTSGMLCCase/src/document.jl`: `const PD = PowerOpenAPIModels`;
  `add!(doc, component) -> Int` (mints via `PD.next_id!` if
  `component.id === nothing`, calls `PD.add_component!`, returns the id)
  — use this instead of Python's `doc.next_id()` + `doc.add_component(...)`
  two-step.
- **Supplemental attributes are simpler in Julia than Python.**
  `PowerOpenAPIModels.add_supplemental_attribute!(doc, attribute,
  component_id::Integer)` already exists (in
  `PowerOpenAPIModels/PowerOpenAPIModels.jl/src/document.jl`, function
  `add_supplemental_attribute!`) — it resolves `component_type` itself
  from `doc.component_types_by_id`, so you do **not** need to pass it,
  and you do **not** need to build a Python-style bespoke wrapper. The
  attribute's own `id` must be minted first (it is not bucketed via
  `add_component!`, so `add!` is the wrong call for it) — mint it
  directly: `attribute.id = PD.next_id!(doc)`, then call
  `PD.add_supplemental_attribute!(doc, attribute, component_id)`.
- `julia/RTSGMLCCase/src/topology.jl`'s `TopologyIndex` struct
  (`bus_id_by_number`, `area_id_by_name`, `zone_id_by_name`) is the
  operations index this stage consumes — read it, don't touch it.
- The investments model structs (`Node`, `Zone`, `TopologyMapping`) live
  in `PowerInvestmentsOpenAPIModels` — already a declared dependency of
  `julia/RTSGMLCCase/Project.toml` (`[sources]` path pin), no
  `Project.toml` edit needed. Check
  `PowerOpenAPIModels/PowerInvestmentsOpenAPIModels.jl/src/models/model_Node.jl`,
  `model_Zone.jl`, `model_TopologyMapping.jl` for their exact
  keyword-constructor field names (`Base.@kwdef mutable struct ... <:
  OpenAPI.APIModel`) — every field is a keyword argument, same idiom as
  every other Julia model in this codebase.
- Confirm whether `PD` re-exports these investments types directly
  (check `PowerOpenAPIModels.jl`'s own module body / `using` statements)
  or whether you need `using PowerInvestmentsOpenAPIModels:
  PowerInvestmentsOpenAPIModels` (or `Node, Zone, TopologyMapping`
  directly) at the top of your new file — follow whichever pattern
  `julia/RTSGMLCCase/src/generation.jl` or `branches.jl` already uses for
  a domain-specific type not on `PD` directly (if any), for consistency.

## What to build (port from `investments/topology.py` exactly — same
## logic, same sorted-order determinism, same R38 zone ruling)

- `julia/RTSGMLCCase/src/investments/data.jl` (or
  `julia/RTSGMLCCase/src/investments_data.jl` if this package doesn't use
  subdirectories under `src/` for submodules — check how `data.jl`/
  `topology.jl` etc. are laid out today: flat under `src/`, not nested —
  **match that flat layout**, i.e. this task's new files are flat under
  `src/` too, e.g. `src/investments_data.jl`, `src/investments_topology.jl`
  — do not introduce a `src/investments/` subdirectory unless the
  existing package already has precedent for nested modules (it doesn't,
  per the file listing above)).
- `investments_source_dir(repo_root=REPO_ROOT) -> String` — same
  validate-only-no-download behavior as the Python
  `investments_source_dir()` (checks the same 16 required files listed
  in Python's `investments/data.py`'s `REQUIRED_FILES` tuple — port that
  exact list), raising `error(...)` (not returning a sentinel) if the
  directory is missing or incomplete, naming every missing path. No
  download — same comment Python's module carries about no verified
  upstream URL this session.
- `add_investment_topology!(doc, source::AbstractString, idx::TopologyIndex)
  -> InvestmentTopologyIndex` where `struct InvestmentTopologyIndex;
  node_id_by_bus_number::Dict{Int,Int}; zone_id_by_name::Dict{String,Int};
  zone_id_by_bus_number::Dict{Int,Int}; end` (mirrors Python's dataclass
  fields exactly).
  - Reads the **operations** `bus.csv` (via
    `RTSGMLCCase.rts_source_dir()`, not `investments_source_dir()` — same
    as Python, the `source` parameter here is unused, mirror Python's `del
    source`-equivalent: just don't reference the parameter, or name it
    `_source` per Julia convention for an intentionally-unused argument —
    check whether this codebase has an existing convention for
    intentionally-unused arguments before picking one).
  - One `Node` per bus (73 total): `name` = the bus's name (same value
    `ACBus.name` got), `bus_type` = the same bustype-normalization
    `topology.jl`'s `_normalize_bustype` already applies — **reuse that
    function** (it's private/lowercase-underscore per Julia convention
    but same-module-tree accessible; check whether it needs to be
    exported or whether direct qualified access
    `RTSGMLCCase._normalize_bustype` works fine from a sibling file in
    the same module — it should, since Julia modules share one
    namespace across all their `include`d files, unlike Python's
    per-file private-name visibility rules that required E1's Python
    port to reason about `from rts_gmlc_case.topology import
    _normalize_bustype`). This is a case where Julia's module model
    makes something easier than the Python port had to work around —
    don't add an unnecessary import shim.
  - One `Zone` per RTS *Area* (R38 — 3 total, named `"1"`/`"2"`/`"3"`,
    **not** per the 21-value `Zone` column and **not** per
    `hierarchy_rts.csv`'s 5-value `ba` column), added in sorted order.
  - One `TopologyMapping` supplemental attribute per `Zone`, `buses` =
    the sorted list of bus **names** in that zone, attached via
    `PD.add_supplemental_attribute!(doc, mapping, zone_id)` (component
    type resolved automatically, per the API note above — unlike
    Python's version, do not pass a `component_type` string).

## Verify (port the Python test file's assertions —
## `python/tests/test_investments_topology.py` and
## `python/tests/test_investments_data.py` — into new Julia test files)

- `julia/RTSGMLCCase/test/test_investments_data.jl`,
  `julia/RTSGMLCCase/test/test_investments_topology.jl` — same shape of
  assertions as the Python tests (73 nodes, 3 zones, zone names exactly
  `{"1","2","3"}` and disjoint from the 5 `hierarchy_rts.csv` `ba` codes,
  every bus in exactly one `TopologyMapping.buses` list, node<->bus
  correspondence).
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean after each
  new file.
- `julia --project=test test/runtests.jl` passes in full (including
  every pre-existing test — no regression).
- Update `julia/RTSGMLCCase/src/RTSGMLCCase.jl` to `include` the two new
  files (after `topology.jl`, since this stage depends on it), and
  `julia/RTSGMLCCase/test/runtests.jl` to include the two new test files.

## Report

Write your full report to `.claude/plans/task-JE1-report.md`. Reply with
only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, the compile/test
commands and pass counts, and a one-line pointer to the report file.

State clearly: the exact file layout you chose (flat under `src/` vs
nested, per the note above), whether `_normalize_bustype` was reused
directly or needed any change to be reachable, and confirmation that the
72 non-topology tests (branches/generation/demand/sidecar/timeseries/
build, if those exist by the time you run) still pass unchanged.

If the Julia operations tutorial isn't actually complete yet when you
start (missing `demand.jl`/`sidecar.jl`/`timeseries.jl`/`build.jl`),
report BLOCKED immediately rather than guessing at what they'd contain —
don't build them as part of this task.