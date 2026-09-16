# Task E6 — Combined driver, round-trip, validation (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md`. Progress
ledger: `.claude/plans/2026-09-01-capacity-expansion-progress.md` — Tasks
E1-E5 are done; read every ledger entry before starting, especially the
"Ruling" entries (AC transport duplicate-pair count of 108,
`prime_mover_type` enum-default trap, `power_systems_type` conventions).
This is the task that wires every earlier stage together — read
`.claude/plans/task-E1-report.md` through `task-E5-report.md` in full,
not just the ledger summaries, since you need every earlier stage's exact
function signature.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`julia/`.

## A required `document.py` extension you must make (not optional, this
## task will fail without it)

`CaseDocument.typed_components()` re-parses `document.components` via a
registry built from `_MODEL_MODULES = ("core", "operations", "timeseries",
"infrastructure_core")` — **`"investments"` is missing from this tuple.**
Every investments component type (`Node`, `Zone`, `SupplyTechnology`,
`StorageTechnology`, `NodalACTransportTechnology`,
`NodalHVDCTransportTechnology`, `DemandRequirement`, the 6 policy types)
will fail to re-parse on read-back without this fix — `typed_components()`
will raise `KeyError` on the first investments type it hits. Add
`"investments"` to `_MODEL_MODULES` in `document.py`. This is the one
existing-file edit this task needs beyond the two new files below; if you
find you need another, stop and report NEEDS_CONTEXT.

`document.supplemental_attributes` stays untyped by design (per
`document.py`'s own docstring) — `TopologyMapping`/`ExistingDevices` are
not expected to come back typed from `typed_components()`; that's correct,
not a gap to fix.

## Every earlier stage's signature (assembled here so you don't have to
## re-derive it from five separate reports — but verify each import
## resolves before relying on it)

Operations (existing, in `rts_gmlc_case`, unchanged — mirror
`rts_gmlc_case/build.py`'s exact stage order, don't re-derive it):

```python
source = rts_gmlc_case.data.rts_source_dir() / "SourceData"
doc = CaseDocument()
idx = rts_gmlc_case.topology.add_topology(doc, source)
rts_gmlc_case.branches.add_branches(doc, source, idx)
gen_ids = rts_gmlc_case.generation.add_generation(doc, source, idx)
rts_gmlc_case.demand.add_loads(doc, source, idx)
reserve_ids = rts_gmlc_case.demand.add_reserves(doc, source, idx, gen_ids)
sidecar = rts_gmlc_case.sidecar.SidecarWriter(case_dir)
owners = rts_gmlc_case.timeseries.TimeSeriesOwners(
    generator_id_by_uid=gen_ids,
    area_id_by_name=idx.area_id_by_name,
    reserve_id_by_product=reserve_ids,
)
rts_gmlc_case.timeseries.attach_time_series(doc, source, sidecar, owners)
```

Investments (E1-E5, new):

```python
inv_source = rts_gmlc_case.investments.data.investments_source_dir()
inv_idx = rts_gmlc_case.investments.topology.add_investment_topology(doc, inv_source, idx)
supply_ids = rts_gmlc_case.investments.technologies.add_supply_technologies(doc, inv_source, idx, inv_idx)
storage_ids = rts_gmlc_case.investments.storage.add_storage_technologies(doc, inv_source, inv_idx)
ac_ids, hvdc_ids = rts_gmlc_case.investments.transport.add_transport_technologies(doc, inv_source, inv_idx)
rts_gmlc_case.investments.demand.add_demand_requirements(doc, inv_source, sidecar, inv_idx)
rts_gmlc_case.investments.policy.add_policy_constraints(doc, supply_ids, storage_ids)
```

**Critical: reuse the SAME `sidecar` (`SidecarWriter`) instance for both
`attach_time_series` and `add_demand_requirements`** — one `timeseries/`
directory, one content-addressed store, for the whole combined case. Do
not construct a second `SidecarWriter`.

**Stage order is fixed and load-bearing, exactly as shown above**
(operations stages in their existing order, then every investments stage
in E1→E2→E3→E4→E5 order) — the plan requires this for id-sequence parity
with the eventual Julia build (Task JE7's cross-language check depends on
it). Verify each function name/signature above against the actual
current source before calling it (earlier tasks' reports may have named
something slightly differently than shown here — trust the code, not
this summary, if they disagree) — if a name here doesn't match what
actually exists, that's worth a one-line note in your report, not a
silent workaround.

## New files

- `python/src/rts_gmlc_case/investments/build.py`
- `python/build_expansion.py` (CLI, mirrors `python/build_rts.py` — read
  it for the exact shape: argv parsing, printed component counts sorted
  by type name, parquet file count)
- `python/tests/test_investments_build.py`
- (extend) `python/src/rts_gmlc_case/document.py` — the one-line
  `_MODEL_MODULES` fix above

## `build_expansion_case(case_dir) -> CaseDocument`

Runs every stage above in order on one `CaseDocument`, then
`doc.validate()`, then `case_dir.mkdir(parents=True, exist_ok=True)` and
`doc.write(case_dir / "system.json")` (reuse `rts_gmlc_case.build`'s
`SYSTEM_FILENAME` constant, don't redefine it). Returns the built `doc`.

## `read_expansion_case(case_dir) -> CaseDocument`

Same shape as `rts_gmlc_case.build.read_case` (`CaseDocument.read(...)`,
then `.typed_components()`, then `.validate()`) — this only works once the
`_MODEL_MODULES` fix above is in place. You may import and reuse
`rts_gmlc_case.build.read_case` directly if its signature already does
exactly this (check first; if it's generic enough, don't duplicate it).

## Prove (the plan's exact words — each needs a real test, not just a
## comment)

- **Byte-determinism across two builds.** Build the case twice into two
  separate temp directories from the same source data, and assert
  `(dir1 / "system.json").read_bytes() == (dir2 / "system.json").read_bytes()`.
  Also assert the two `timeseries/` directories contain the same set of
  filenames (content-addressed, so this follows from determinism, but
  check it explicitly rather than assuming).
- **Id uniqueness across both halves.** `doc.validate()` already checks
  global id uniqueness across every bucket (confirmed by reading
  `document.py`), so this is covered by `validate()` passing — but add an
  explicit test that asserts the union of every component's `id` across
  *all* buckets has no duplicates AND spans both operations-only type
  names (e.g. `ACBus`, `ThermalStandard`) and investments-only type names
  (e.g. `Node`, `SupplyTechnology`) in one continuous id space (e.g.
  assert the max operations-side id and min investments-side id
  interleave sensibly with the build order, or just assert one global
  `set` of ids has length equal to the total component count — the
  simpler check is fine, the point is proving it's not two independent
  counters that happen not to collide by luck).
- **Every investment reference resolves to a component in the same
  document.** `validate()` does NOT check `region`, `start_node`,
  `end_node`, or `requirements` (confirmed: none of these are in
  `document.py`'s `_REFERENCE_FIELDS`) — write a dedicated integration
  test against the full combined document that checks every one of these
  fields on every investments component resolves to a real id somewhere
  in `doc.document.components`. This is the global version of checks
  E2/E3/E5 already did in isolation — do it again here across the real,
  fully-combined document as an end-to-end guarantee.
- **Sidecar has no orphans.** Every file under `case_dir/timeseries/` is
  referenced by at least one `time_series_associations` row's `uri`, and
  every `uri` in `time_series_associations` points to a file that
  actually exists. Check both directions.
- **`power_systems_type` values all name types present in the document.**
  Across every investments component with a `power_systems_type` field
  (`SupplyTechnology` x9, `StorageTechnology` x1,
  `NodalACTransportTechnology` x108 -> `"Line"`,
  `NodalHVDCTransportTechnology` x1 -> `"TwoTerminalGenericHVDCLine"`,
  `DemandRequirement` x3 -> `"PowerLoad"`), assert the string is a key in
  `doc.document.components` with a nonempty list. (E2 already proved this
  for its own 9 classes against a partial document; this is the same
  check against the real, complete one — should trivially pass if
  everything upstream is correct, but prove it here too.)

## Build the real case

Call `build_expansion_case("cases/rts-expansion")` for real (not just in
a test) and report the resulting component counts (mirror
`build_rts.py`'s printed-counts format) in your report. This is the
plan's actual deliverable — `cases/rts-expansion/system.json` +
`cases/rts-expansion/timeseries/` must exist on disk when you're done,
built from the real downloaded data, not just exercised inside a test
against a temp dir.

Do not touch `cases/rts-python/` (the existing operations-only case) —
this is a new, separate directory.

## Test markers

Mark the full-combined-build tests (the ones that actually run
`build_expansion_case` end-to-end, reading all real source data) `slow`,
consistent with the operations suite's convention (`pytest.ini_options`
marker `slow`, deselected with `-m "not slow"`). Tests that only exercise
`read_expansion_case` against a small fixture, or that check the
`_MODEL_MODULES` fix in isolation, don't need the marker if they're fast.

## Report

Write your full report to
`.claude/plans/task-E6-report.md`. Run the fast suite first
(`cd python && uv run pytest -m "not slow" -v`) to confirm no regression,
then run the slow build test(s) explicitly (`uv run pytest
tests/test_investments_build.py -v` without `-m "not slow"`, since this
task's own new tests are exactly the ones that need to run un-deselected
here) and report their wall-clock time, then `uv run pytest -m "not slow"
-W error::UserWarning -q` for the warning-clean gate. Reply with only
DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, the exact commands
and pass counts, the final component-count table from the real
`cases/rts-expansion/` build, and a one-line pointer to the report file.

State clearly in the report: the final total component count and
per-type breakdown for `cases/rts-expansion/`, confirmation that
`cases/rts-python/` was left untouched, and any signature mismatch you
found between this brief's assembled call sequence and the actual
current code.

This is the last Python task before the Julia mirror — if anything here
reveals a defect in an earlier task's output (not just an ambiguity),
say so explicitly rather than quietly working around it, since it may
need a ruling recorded in the ledger before the Julia side mirrors the
same behavior.