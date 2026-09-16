# Task E6 report — Combined driver, round-trip, validation (Python)

## Status: DONE

## Important finding: the previous (rate-limited) attempt had already written two of this task's files

The ledger (`2026-09-01-capacity-expansion-progress.md`) states the killed
attempt's "partial progress was not committed/saved -- no files were
written yet per its own last message." That was incorrect. On starting
this task fresh, two files already existed on disk, with mtimes
(`document.py` 10:12:06, `investments/build.py` 10:12:55) landing right
before the ledger's own "~10:18am" rate-limit timestamp:

- `python/src/rts_gmlc_case/document.py` — `_MODEL_MODULES` already
  included `"investments"`.
- `python/src/rts_gmlc_case/investments/build.py` — already contained a
  complete `build_expansion_case`/`read_expansion_case` implementation.

I did not assume these were correct — I read both in full and verified
every call inside `investments/build.py` against the actual current
signature of each stage function (`add_investment_topology`,
`add_supply_technologies`, `add_storage_technologies`,
`add_transport_technologies`, `add_demand_requirements`,
`add_policy_constraints`), confirmed the stage order matches the brief's
required E1→E2→E3→E4→E5 sequence exactly, confirmed the single shared
`SidecarWriter` instance is reused for both `attach_time_series` and
`add_demand_requirements`, and confirmed `read_expansion_case` correctly
delegates to `rts_gmlc_case.build.read_case` rather than duplicating it (as
the brief allows). All of it was correct and needed no changes beyond one
docstring wording fix (see below). I built on it rather than rewriting it,
since rewriting working, verified code identical to the brief's own spec
would have been pure churn.

**This is a process discrepancy worth recording in the ledger**, not a
content defect: the previous session's self-report of "no files written"
was wrong, and a future resume-from-ledger reader should not trust "no
files were written yet" claims without checking `stat`/mtimes against the
claimed kill time, as I did here.

## Files touched

New:
- `python/build_expansion.py` — CLI, exact mirror of `python/build_rts.py`'s
  shape (argv parsing, usage-error exit code, sorted printed component
  counts, `service_associations`/`time_series_associations`/parquet-file
  counts), calling `rts_gmlc_case.investments.build.build_expansion_case`
  instead of `rts_gmlc_case.build.build_case`.
- `python/tests/test_investments_build.py` — 8 tests (7 marked `slow`, 1
  fast CLI-usage test), covering every proof the brief requires (see
  below).

Extended:
- `python/src/rts_gmlc_case/document.py` — one docstring-only fix beyond
  the `_MODEL_MODULES` addition that was already present:
  `typed_components()`'s docstring still said "a registry built from
  `core`, `operations`, `timeseries`, and `infrastructure_core`" (stale —
  missing `investments`, which the already-present code change had already
  added to the actual `_MODEL_MODULES` tuple). Corrected the docstring to
  list `investments` too. No behavior change; the fix that matters
  (`_MODEL_MODULES` itself) was already in place before I started.

Verified pre-existing (not modified further):
- `python/src/rts_gmlc_case/investments/build.py`.

`cases/rts-python/` was left untouched (confirmed: `system.json`'s own
mtime is unchanged from before this session; only its parent `cases/`
directory's mtime changed, from gaining the new `rts-expansion/` sibling
entry). `julia/` was not touched. No `git add`/`git commit`/git write was
run at any point.

## Signature/name mismatches found between the brief and actual code: none

Every function name and signature in the brief's "assembled call sequence"
section matched the actual current source exactly:
`add_investment_topology(doc, source, idx)`,
`add_supply_technologies(doc, source, idx, inv_idx)`,
`add_storage_technologies(doc, source, inv_idx)`,
`add_transport_technologies(doc, source, inv_idx) -> (ac_ids, hvdc_ids)`,
`add_demand_requirements(doc, source, sidecar, inv_idx)`,
`add_policy_constraints(doc, supply_ids, storage_ids)`. No workaround or
deviation was needed.

## The 6 required proofs — how each was implemented

All in `python/tests/test_investments_build.py`, against a module-scoped
`built_case` fixture that runs one real `build_expansion_case` into a temp
dir (shared across the read-only tests; the determinism test additionally
runs a second independent build):

1. **Byte-determinism across two builds** —
   `test_build_is_byte_deterministic`: builds twice into separate temp
   dirs, asserts `system.json` bytes are identical, and separately asserts
   the two `timeseries/` directories contain the same *set* of `.parquet`
   filenames (non-empty, checked explicitly rather than inferred).
2. **Id uniqueness across both halves** —
   `test_id_uniqueness_spans_operations_and_investments_in_one_continuous_space`:
   builds one global `set` of every component id across every bucket,
   asserts its length equals the total component count (no bucket-local id
   reuse), and additionally proves the ids are one continuous counter (not
   two independent ones) by asserting every `ACBus`/`ThermalStandard`
   (operations-only types) id is smaller than every `Node`/
   `SupplyTechnology` (investments-only types) id, consistent with
   operations stages running first in the fixed build order.
3. **Every investment reference resolves inside the same document** —
   `test_every_investment_reference_resolves_to_a_component_in_the_document`:
   checks `region`/`requirements` on `SupplyTechnology`, `StorageTechnology`,
   `DemandRequirement`, and `start_node`/`end_node`/`requirements` on
   `NodalACTransportTechnology`/`NodalHVDCTransportTechnology`, against the
   full combined document's global id set. (The 6 policy types have no
   reference fields of their own — confirmed by reading
   `power_openapi_models/investments/models.py` directly — so they're
   correctly excluded from this check, not silently skipped.)
4. **Sidecar has no orphans** —
   `test_sidecar_has_no_orphans_in_either_direction`: checks both
   directions — every `time_series_associations` `uri` resolves to a file
   that exists, and the set of files actually on disk under
   `timeseries/*.parquet` equals exactly the set of referenced paths (no
   orphan files, no dangling references).
5. **`power_systems_type` values all name types present in the document** —
   `test_power_systems_type_values_all_name_types_present_in_the_document`:
   checks all 9 distinct `SupplyTechnology` values individually (varies by
   tech class per R39) plus the fixed one-value-per-type checks for
   `StorageTechnology` ("EnergyReservoirStorage"),
   `NodalACTransportTechnology` ("Line"), `NodalHVDCTransportTechnology`
   ("TwoTerminalGenericHVDCLine"), and `DemandRequirement` ("PowerLoad"),
   against the real, complete combined document (not a partial one, unlike
   E2's own isolated version of this check).
6. **`document.py`'s `_MODEL_MODULES` fix, proven, not just asserted** —
   `test_round_trip_typed_components_match_bucket_by_bucket`: runs
   `read_expansion_case` (which calls `typed_components()`) against the
   just-built case and asserts every investments bucket
   (`Node`/`Zone`/`SupplyTechnology`/`StorageTechnology`/
   `NodalACTransportTechnology`/`NodalHVDCTransportTechnology`/
   `DemandRequirement`/all 6 policy types) round-trips byte-for-byte
   through a full write/read cycle, alongside every operations bucket.
   Without the `_MODEL_MODULES` fix already in place, this test would raise
   `KeyError` on the first investments type it hits, per the brief's
   warning.

Also included (fixed, from mirroring `test_build.py`'s own component-count
assertion): `test_expansion_build_produces_expected_component_counts`
checks the exact merged operations+investments count dict plus
`service_associations`/`time_series_associations` totals.

## Test commands and results

```
cd python && uv run pytest -m "not slow" -v
```
→ **124 passed, 12 deselected** in 15.95s–16.4s (varied slightly run to
run; both runs 0 failed). Reconciles exactly with the ledger's E5 baseline
of 123 passed, 5 deselected: this task adds 8 new tests total (7 newly
`slow`-marked + 1 fast), so 123+1=124 passed and 5+7=12 deselected.

```
cd python && uv run pytest tests/test_investments_build.py -v
```
→ **8 passed in 5.75s** (wall-clock). All 7 slow-marked tests plus the 1
fast CLI test, run un-deselected as the brief requires.

```
cd python && uv run pytest -m "not slow" -W error::UserWarning -q
```
→ **124 passed, 12 deselected** in 16.40s, 0 warnings surfaced as errors —
the suite stays warning-clean.

No `git add`/`git commit`/git write was run at any point. `git status
--porcelain` at the workspace root confirms `python/` shows only as its
pre-existing single untracked entry (`?? python/`), and `cases/` does not
appear at all (already `.gitignore`d at the workspace root), so the new
`cases/rts-expansion/` output is correctly invisible to git, same as the
pre-existing `cases/rts-python/`.

## The real deliverable: `cases/rts-expansion/`

Built via, from `python/` (mirroring the operations tutorial's own
`../cases/rts-python` convention, since `cases/` lives at the workspace
root, not under `python/`):

```
uv run python build_expansion.py ../cases/rts-expansion
```

Output confirmed on disk: `cases/rts-expansion/system.json` (773 KB) and
`cases/rts-expansion/timeseries/` (149 parquet files). `cases/rts-python/`
confirmed untouched (its `system.json`'s own mtime is unchanged from
before this session).

### Final component-count table (`cases/rts-expansion/`)

| type | count | half |
|---|---:|---|
| ACBus | 73 | operations |
| Arc | 109 | operations |
| Area | 3 | operations |
| CapacityReserveMargin | 1 | investments (E5) |
| CarbonCaps | 4 | investments (E5) |
| CarbonTax | 1 | investments (E5) |
| DemandRequirement | 3 | investments (E4) |
| EnergyReservoirStorage | 1 | operations |
| EnergyShareRequirements | 1 | investments (E5) |
| FixedAdmittance | 3 | operations |
| HydroDispatch | 20 | operations |
| Line | 105 | operations |
| LoadZone | 21 | operations |
| MaximumCapacityRequirements | 1 | investments (E5) |
| MinimumCapacityRequirements | 1 | investments (E5) |
| NodalACTransportTechnology | 108 | investments (E3) |
| NodalHVDCTransportTechnology | 1 | investments (E3) |
| Node | 73 | investments (E1) |
| OnlineReserve | 7 | operations |
| PowerLoad | 51 | operations |
| RenewableDispatch | 30 | operations |
| RenewableNonDispatch | 31 | operations |
| StorageTechnology | 1 | investments (E3) |
| SupplyTechnology | 9 | investments (E2) |
| SynchronousCondenser | 3 | operations |
| ThermalStandard | 73 | operations |
| TransformerCircuit | 15 | operations |
| TwoTerminalGenericHVDCLine | 1 | operations |
| TwoWindingTransformer | 15 | operations |
| Zone | 3 | investments (E1) |
| **Total components** | **768** | (561 operations + 207 investments) |

Also: `service_associations`: 510 (operations only, unchanged);
`time_series_associations`: 285 (282 operations + 3 investments
`DemandRequirement` series); `supplemental_attributes`: 13 (3
`TopologyMapping` from E1 + 9 `ExistingDevices` from E2 + 1
`ExistingDevices` from E3), each with a matching
`supplemental_attribute_associations` row; parquet files on disk: 149.

## Defects found in earlier tasks: none

Nothing in E1-E5's output required a workaround or contradicted this
task's assumptions. The one genuine surprise was procedural (the ledger's
"no files written" claim, addressed above), not a defect in any earlier
task's actual production code or test coverage.

## Ambiguities encountered

None load-bearing enough to stop and ask. The workspace-root-vs-`python/`
relative path for `cases/rts-expansion/` (the brief's literal
`build_expansion_case("cases/rts-expansion")` reads as relative to
`python/`, but the pre-existing `cases/rts-python/` sibling case lives at
the workspace root) was resolved by following the same convention the
operations tutorial's own docs/plan already established
(`uv run python build_rts.py ../cases/rts-python`, confirmed via
`docs/08-validation.md` and the original Python tutorial plan) rather than
guessing — not a new call, just applying the existing precedent.
