# Task JE6 — Julia mirror of E6: combined driver, round-trip, validation

Mirrors `python/src/rts_gmlc_case/investments/build.py` into Julia:
combines every operations + investments stage into one driver, proves
several cross-cutting correctness properties, and builds the real
deliverable case into `cases/rts-julia-expansion/`. Assumes **JE1
through JE5 are all done and merged**. If any isn't, report BLOCKED.

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `python/`. Do not change `PowerOpenAPIModels`'s checkout. Do
not touch `cases/rts-julia/` (the existing operations-only case) — this
task creates a new, separate `cases/rts-julia-expansion/` directory (the
Julia-side counterpart to Python's `cases/rts-expansion/`).

## Good news: no registry fix needed in Julia (unlike Python's E6)

Python's E6 needed a `document.py` fix (`_MODEL_MODULES` missing
`"investments"`) because Python's `typed_components()` re-parse is keyed
by a hand-maintained tuple of module names. **Julia's equivalent
(`document_from_json`/`read_document`) has no such tuple** — it resolves
every component type through
`InfrastructureCoreOpenAPIModels.model_type(type_name)`, a package-wide
registry every domain package (including `PowerInvestmentsOpenAPIModels`)
populates automatically at load time via its generated `register.jl`.
Confirmed by reading `PowerOpenAPIModels.jl/src/document.jl` directly.
**You should not need to modify any existing `src/*.jl` file for this
task** — if `read_case` fails to round-trip an investments type, that's
a real bug worth investigating (missing registration, wrong package
load order), not something to route around by adding a registry
yourself; report it rather than guessing at a fix.

## The exact combined stage order (mirrors `build.jl`'s existing
## `build_case`, then appends every investments stage in JE1→JE2→JE3→
## JE4→JE5 order — same order Python's E6 uses, load-bearing for JE7)

```julia
function build_expansion_case(case_dir::AbstractString)
    source = joinpath(rts_source_dir(), SOURCE_DATA)
    inv_source = investments_source_dir()

    doc = new_document()

    # Operations half (unchanged from build_case).
    idx = add_topology!(doc, source)
    add_branches!(doc, source, idx)
    gen_ids = add_generation!(doc, source, idx)
    add_loads!(doc, source, idx)
    reserve_ids = add_reserves!(doc, source, idx, gen_ids)

    sidecar = SidecarWriter(case_dir)
    owners = TimeSeriesOwners(gen_ids, idx.area_id_by_name, reserve_ids)
    attach_time_series!(doc, source, sidecar, owners)

    # Investments half (JE1 -> JE2 -> JE3 -> JE4 -> JE5), same document, same sidecar.
    inv_idx = add_investment_topology!(doc, inv_source, idx)
    supply_ids = add_supply_technologies!(doc, inv_source, idx, inv_idx)
    storage_ids = add_storage_technologies!(doc, inv_source, inv_idx)
    add_transport_technologies!(doc, inv_source, inv_idx)
    add_demand_requirements!(doc, inv_source, sidecar, inv_idx)
    add_policy_constraints!(doc, supply_ids, storage_ids)

    PD.validate_document(doc)
    mkpath(case_dir)
    PD.write_document(doc, joinpath(case_dir, SYSTEM_FILENAME); pretty = true, force = true)

    return doc
end
```

**Verify every function name/signature above against the actual current
source before relying on it** — this is assembled from reading each
JE1-JE5 file, but confirm directly (`grep -n "^function add_"` across
the new `investments_*.jl` files) rather than trusting this brief
blindly; note any mismatch in your report. **Critical: reuse the SAME
`sidecar` (`SidecarWriter`) instance for both `attach_time_series!` and
`add_demand_requirements!`** — exactly as Python's E6 does.

`read_expansion_case(case_dir) = read_case(case_dir)` — reuse `build.jl`'s
existing generic `read_case` directly (it doesn't hand-maintain a type
registry, so it should already work unmodified for investments types —
see above).

## New files (flat under `src/`)

- `julia/RTSGMLCCase/src/investments_build.jl`
- `julia/RTSGMLCCase/build_expansion.jl` (CLI, mirrors
  `julia/RTSGMLCCase/build_rts.jl`'s shape exactly)
- `julia/RTSGMLCCase/test/test_investments_build.jl`
- Update `RTSGMLCCase.jl`/`test/runtests.jl` includes (last, after every
  other investments file).

## Prove (port Python E6's 6 required proofs into Julia tests — read
## `python/tests/test_investments_build.py` for the exact shape of each)

1. **Byte-determinism** across two independent builds into two temp
   dirs — compare `system.json` bytes.
2. **Id uniqueness across both halves** — one continuous id space, not
   two independent counters (check via `PD.` internals or by collecting
   every component's `.id` across every type bucket into one `Set` and
   comparing its length to the total component count).
3. **Every investment reference resolves inside the same document** —
   `region`/`requirements`/`start_node`/`end_node` on every investments
   component, checked against the full combined document's id space
   (`PD.validate_document` does not check these non-standard reference
   fields — verify this claim yourself against `document.jl` rather than
   assuming, then write the dedicated check).
4. **Sidecar has no orphans** — every `time_series_associations` `uri`
   resolves to an existing file, and every file under
   `timeseries/*.parquet` is referenced by at least one association.
5. **`power_systems_type` values all name types present in the
   document** — check all 9 `SupplyTechnology` values, plus
   `StorageTechnology`/`NodalACTransportTechnology`/
   `NodalHVDCTransportTechnology`/`DemandRequirement`'s fixed values,
   against the real combined document.
6. **Round-trip**: `read_expansion_case` reproduces every component
   bucket, including every investments type, matching Python's
   equivalent proof that the registry/re-parse path actually works for
   investments types (this is Julia's analogue of proving the
   `_MODEL_MODULES` fix worked on the Python side, even though Julia
   needed no equivalent fix — still worth an explicit test, not just an
   assumption).

## Build the real case

`build_expansion_case(joinpath(REPO_ROOT, "cases", "rts-julia-expansion"))`
— for real, not just in a test. Report the resulting component-count
table (mirror `build_rts.jl`'s printed-counts format via
`build_expansion.jl`) and compare it directly against Python's
`cases/rts-expansion/system.json` (768 total components, 285
time_series_associations, 510 service_associations, 13
supplemental_attributes — read `.claude/plans/task-E6-report.md` for
the exact reference table) — **every count should match exactly**; if
any doesn't, that's a real finding to investigate and report, not
something to silently paper over.

## Test markers

This package has no formal `@testset "slow"`-vs-fast split visible in
its existing tests (check — the Python side uses a pytest marker, Julia
may not have an equivalent convention here); if there is no existing
convention for marking slow tests, don't invent one — just note in your
report that the new build tests run a real full build and take
proportionally longer, same as every other stage's tests already do in
this package's `runtests.jl`.

## Report

Write your full report to `.claude/plans/task-JE6-report.md`. Run the
full test suite (`julia --project=test test/runtests.jl`, backgrounded,
actually wait for and read its result) and report the pass count, plus
the real `cases/rts-julia-expansion/` component-count table compared
directly against Python's `cases/rts-expansion/` counts. Reply with only
DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, compile/test
commands and pass counts, the count-comparison table, and a one-line
pointer to the report file.

If anything here is ambiguous, or you find a defect in an earlier
JE1-JE5 task's output rather than just an ambiguity, ask before
guessing — this is the integration point where earlier tasks' mistakes
first surface, same as Python's E6 was.