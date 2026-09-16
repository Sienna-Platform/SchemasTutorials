# Task JO6-9 report — Julia operations tutorial: demand, sidecar, time series, build driver

Status: **DONE**

## Summary

Finished `julia/RTSGMLCCase/` to parity with `python/src/rts_gmlc_case/`: added
`demand.jl`, `sidecar.jl`, `timeseries.jl`, `build.jl`, `build_rts.jl`, and their
tests. Along the way, hit and resolved (with the coordinator's explicit rulings)
two significant discovered blockers that were not anticipated by the brief:

1. **Environment**: fresh-resolved cleanly against `PowerOpenAPIModels@main`
   (`0568d41`) — no lingering issue from the earlier wrong-branch manifest.
2. **`generation.jl` was thermal-only** (73/158 units) — a real functional gap,
   not a stale-doc issue. Fixed by implementing the remaining 8 unit-type
   builders (WIND/PV/CSP → `RenewableDispatch`, RTPV → `RenewableNonDispatch`,
   HYDRO/ROR → `HydroDispatch`, SYNC_COND → `SynchronousCondenser`, STORAGE →
   `EnergyReservoirStorage`), ported from `generation.py`, under the
   coordinator's explicit authorization to expand scope beyond the originally
   sanctioned "one small lookup table."
3. **`ThermalStandard` schema drift**: `generation.jl`'s existing
   `_build_thermal_standard` used `status="ONLINE"` / `commitment_mode="COMMITTED"`,
   which no longer exist on `PowerOpenAPIModels@main`'s `ThermalStandard`
   (`status` is now `Bool`, `commitment_mode` was removed, `must_run::Bool` was
   added). Fixed as a 3-line mechanical schema-drift correction, per the
   coordinator's explicit ruling — confirmed as a genuine upstream change (Julia
   ahead of Python; Python's `power_openapi_models` still uses the old shape,
   see "Cross-package version drift" below).

Both discoveries were reported and the coordinator explicitly ruled on both
before I proceeded (transcript above). Nothing here was guessed past.

## Compile / test commands run, with results

```
cd julia/RTSGMLCCase
julia --project=. -e 'using RTSGMLCCase'                      # compiles clean (checked incrementally after every new file)
julia --project=test -e 'using Pkg; Pkg.resolve(); Pkg.instantiate()'
julia --project=test test/runtests.jl                          # 3659 passed, 0 failed, 0 errored — 3m32.6s
julia --project=. build_rts.jl <repo-root>/cases/rts-julia      # real build, see counts below
```

Both `Project.toml` and `test/Project.toml`'s `Manifest.toml` were deleted and
regenerated fresh (the pre-existing backup at
`.claude/plans/RTSGMLCCase-Manifest.toml.bak` and the since-reverted regenerated
one were both discarded, per the task's instruction not to trust either).

## Real `cases/rts-julia/` build — component counts

Built via `julia --project=. build_rts.jl <repo-root>/cases/rts-julia`. Every
count below matches the real `cases/rts-python/` build exactly (compared
directly, component-by-component and association-by-association):

| Component type | Julia | Python |
|---|---|---|
| ACBus | 73 | 73 |
| Arc | 109 | 109 |
| Area | 3 | 3 |
| EnergyReservoirStorage | 1 | 1 |
| FixedAdmittance | 3 | 3 |
| HydroDispatch | 20 | 20 |
| Line | 105 | 105 |
| LoadZone | 21 | 21 |
| OnlineReserve | 7 | 7 |
| PowerLoad | 51 | 51 |
| RenewableDispatch | 30 | 30 |
| RenewableNonDispatch | 31 | 31 |
| SynchronousCondenser | 3 | 3 |
| ThermalStandard | 73 | 73 |
| TransformerCircuit | 15 | 15 |
| TwoTerminalGenericHVDCLine | 1 | 1 |
| TwoWindingTransformer | 15 | 15 |
| **service_associations** | 510 | 510 |
| **time_series_associations** | 282 | 282 |
| **parquet files** | 146 | 146 |

**Stronger check than counts**: the *sets* of `data_hash` values across all 282
time-series associations are identical between the two builds (146 distinct
hashes each, symmetric difference = 0) — the parquet payloads themselves are
byte-for-byte content-equivalent across languages, not just equal in count.
Verified directly:

```python
py_hashes = {a["data_hash"] for a in py_doc["time_series_associations"]}
jl_hashes = {a["data_hash"] for a in jl_doc["time_series_associations"]}
py_hashes == jl_hashes  # True, symmetric diff = 0
```

`cases/rts-julia/` is under the repo-root `cases/` directory (matching
`cases/rts-python/`'s convention, and already covered by the repo's
`.gitignore`), not nested under `julia/`.

## Cross-language pin: `data_hash([1.0, 2.0, 3.0])`

Verified directly against Python before writing the Julia test:

```
$ cd python && uv run python3 -c "from rts_gmlc_case.sidecar import data_hash; import numpy as np; print(data_hash(np.array([1.0,2.0,3.0])))"
a68de4b5e96a60c8ceb3c7b7ef93461725bdbbff3516b136585a743b5c0ec664
```

(This literal was also already present, independently, in
`python/tests/test_sidecar.py::test_pinned_cross_language_hash` — both sources
agree.) Same value reproduced in Julia via `htol.(values)` +
`reinterpret(UInt8, ...)` + SHA-256, asserted literally in
`test/test_sidecar.jl::"pinned cross-language hash"`.

## Files added / changed

New:
- `julia/RTSGMLCCase/src/demand.jl`
- `julia/RTSGMLCCase/src/sidecar.jl`
- `julia/RTSGMLCCase/src/timeseries.jl`
- `julia/RTSGMLCCase/src/build.jl`
- `julia/RTSGMLCCase/build_rts.jl`
- `julia/RTSGMLCCase/test/test_demand.jl`
- `julia/RTSGMLCCase/test/test_sidecar.jl`
- `julia/RTSGMLCCase/test/test_timeseries.jl`
- `julia/RTSGMLCCase/test/test_build.jl`

Changed:
- `julia/RTSGMLCCase/src/generation.jl` — substantially expanded beyond the
  originally-sanctioned "one small lookup table" addition, per the
  coordinator's explicit mid-session ruling (see "Scope expansion" below).
  Added `UNIT_TYPE_TO_TARGET` (the originally-requested public lookup, 12
  entries) + `unit_type_target`, `PRIME_MOVER_BY_UNIT_TYPE` (replaces the old
  4-entry `THERMAL_PRIME_MOVER`), `SYNC_COND_BASE_POWER`, five new builder
  functions (`_build_renewable_dispatch`, `_build_renewable_non_dispatch`,
  `_build_hydro_dispatch`, `_build_synchronous_condenser`,
  `_build_energy_reservoir_storage`) plus their cost-tree helpers, and
  `_storage_head_rows`. `_build_thermal_standard`'s signature gained an unused
  4th `_storage_row` parameter so every entry in `GENERATOR_BUILDERS` shares one
  call shape (mirrors Python's uniform `_BUILDERS` dict). Fixed the
  `ThermalStandard` schema-drift bug (`status`/`must_run` instead of
  `status`/`commitment_mode`). `GENERATOR_BUILDERS` is now keyed by target
  *type name* (6 entries) rather than by `Unit Type` (previously 4 entries).
  `add_generation!` now raises on a truly unmapped `Unit Type` (the "skip
  silently, sibling task hasn't landed" carve-out no longer applies since the
  sibling task is now done).
- `julia/RTSGMLCCase/test/test_generation.jl` — rewritten to mirror
  `python/tests/test_generation.py`'s shape: full 158-unit coverage
  (`"generation counts match gen.csv groupby"`), renewable/hydro/sync-cond/
  storage ratings and conventions, unmapped-unit-type error test. The one
  surviving original assertion changed for the schema fix:
  `unit.status == "ONLINE"` → `unit.status == true` (+ new `unit.must_run ==
  false` assertion). The one call-site changed for the new 4-arg builder
  signature: `_build_thermal_standard(doc, row, 1)` →
  `_build_thermal_standard(doc, row, 1, nothing)`.
- `julia/RTSGMLCCase/src/RTSGMLCCase.jl` — added the four new `include`s in
  dependency order: `demand.jl` (needs `topology.jl`), `sidecar.jl`,
  `timeseries.jl` (needs `sidecar.jl`, and `generation.jl`'s
  `unit_type_target`), `build.jl` (needs everything).
- `julia/RTSGMLCCase/test/runtests.jl` — added the four new test `include`s,
  plus `using Dates`, `using TimeZones`, `using Parquet2` (needed directly by
  the new test files).
- `julia/RTSGMLCCase/Project.toml` / `julia/RTSGMLCCase/test/Project.toml` —
  added `Dates` and `UUIDs` (both Julia stdlibs, needed by `sidecar.jl`/
  `timeseries.jl`; zero version ambiguity). Also added `SHA` and `TimeZones` to
  `test/Project.toml` (needed directly by the new test files; the main
  `Project.toml` already had them). **Flagging per the brief's instruction**:
  these four were *not* pre-anticipated in either `Project.toml`, unlike
  `Parquet2`/`TimeZones`/`JSON3`/`SHA` on the main package — I added them
  because compilation genuinely failed without them, not as a "silently added,
  not sure if right" case; all four are either an already-present main-package
  dep repeated into the test env, or a zero-risk Julia stdlib.
- `julia/RTSGMLCCase/Manifest.toml`, `julia/RTSGMLCCase/test/Manifest.toml` —
  deleted and regenerated fresh via `Pkg.resolve(); Pkg.instantiate()` against
  `PowerOpenAPIModels@main` (`0568d41`), per the task's explicit instruction.
  Neither the pre-existing backup nor the since-reverted regenerated manifest
  was reused as a starting point.

Not touched: `python/`, PowerOpenAPIModels's git checkout,
`src/{data,document,topology,branches}.jl`.

## `PD.add_service_association!` / `PD.add_time_series_association!` — actual signatures used

Confirmed against `PowerOpenAPIModels.jl/src/document.jl` (not the ones
guessed in the brief):

```julia
# document.jl:273 — takes ONE pre-built association object, not two bare ints
function add_service_association!(doc::SystemDocument, assoc::T) where {T <: OpenAPI.APIModel}
    # reads assoc.service_id / assoc.entity_id by property access
end
# called as:
PD.add_service_association!(doc, PD.ServiceAssociation(; service_id = reserve_id, entity_id = gen_ids[uid]))

# document.jl:324 — takes the oneOf wrapper, not the bare SingleTimeSeries
function add_time_series_association!(doc::SystemDocument, assoc::TimeSeriesAssociation)
end
# called as:
PD.add_time_series_association!(doc, PD.TimeSeriesAssociation(single_time_series))
```

`ServiceAssociation` (`PowerOperationsOpenAPIModels.jl/src/models/model_ServiceAssociation.jl`):
`Base.@kwdef mutable struct` with exactly `service_id::Union{Nothing,Int64}`,
`entity_id::Union{Nothing,Int64}` — a plain 2-field association row, matching
the brief's guess in spirit but confirmed to need a constructed object, not
two bare positional ints.

## Every place the 2026-08-28 Julia plan doc disagreed with the actual Python implementation

Beyond the two divergences the brief already flagged (`PT3600S`/`PT300S` →
`PT1H`/`PT5M`; single hardcoded `quantity_kind` → the 5-entry
`PARAMETER_TARGETS` map), I found these additional ones while porting:

1. **`SidecarWriter`'s shape**. The old doc proposes
   `struct SidecarWriter; dir::String; written::Set{String}; end` — a
   `written` cache implying "skip the write if we've already written this
   hash." The actual Python `SidecarWriter` (and its own docstring) explicitly
   rejects that: it re-writes unconditionally on every call, precisely because
   mere prior-existence can't distinguish a valid file from a corrupt/partial
   one from an interrupted run (`test_corrupt_file_at_hash_path_is_replaced`
   pins this). My Julia `SidecarWriter` has no `written` field and always
   writes-then-atomically-replaces, matching the actual behavior, not the old
   doc's guessed optimization.
2. **Atomicity not in the old doc's `write_series!` sketch**. The old doc's
   snippet writes straight to `path` via `Parquet2.writefile(path, ...)` with
   no temp-file dance. The actual Python contract requires atomic
   write-to-temp-then-replace (`os.replace`). Ported as write-to-uniquely-named-
   temp-file-in-same-dir + `mv(...; force=true)`.
3. **`element_type`'s described mechanism**. The old doc's Task 8 section says
   to use "the scalar float member of the generated element-type enum,"
   implying `SingleTimeSeries.element_type` is a typed enum. It is actually a
   plain unconstrained `String` field in the generated
   `InfrastructureTimeSeriesOpenAPIModels` struct (no enum validation on it at
   all) — the correct value is simply the literal string `"f64"`, confirmed
   both from Python's own docstring/tests and from the real
   `cases/rts-python/system.json` on disk.
4. **`Owners`'s shape**. The old doc proposes
   `struct Owners; idx::TopologyIndex; gen_ids::Dict{String,Int};
   reserve_ids::Dict{String,Int}; end` — bundling the *entire* `TopologyIndex`.
   The actual Python `TimeSeriesOwners` only takes the one Dict it needs
   (`area_id_by_name`), not the whole topology index. Ported as three flat
   `Dict`s (`generator_id_by_uid`, `area_id_by_name`, `reserve_id_by_product`),
   matching Python exactly.
5. **`component_field` from the `Parameter` map**. The old doc says
   "`name`/`component_field` from `Parameter` via an explicit map" — implying
   both fields are populated from the map. The actual Python code only ever
   sets `name`; `component_field` is never passed (stays `None`/unset). Ported
   the same way — `component_field` is never set.
6. **`GENERATOR_BUILDERS`'s dispatch key** (not from the 2026-08-28 doc, but
   worth recording as a real, not merely cosmetic, structural fact): the
   pre-existing Julia `GENERATOR_BUILDERS` dict was keyed directly by `Unit
   Type` (4 entries: NUCLEAR/STEAM/CT/CC → `_build_thermal_standard`). Once
   all 12 `Unit Type`s needed dispatch, I restructured it to be keyed by
   *target component type name* (6 entries, one per distinct struct), matching
   Python's actual two-dict structure (`UNIT_TYPE_TO_MODEL`/`unit_type_target`
   for the name lookup, `_BUILDERS` for the builder lookup) rather than
   Python's flatter single-dict alternative it could have used instead.

## Cross-package version drift (worth a prominent, separate note)

`PowerOpenAPIModels@main`'s generated `ThermalStandard`
(`PowerOperationsOpenAPIModels.jl`) and Python's `power_openapi_models`'
`ThermalStandard` have **drifted out of sync** on this one type's exact field
set:

- Julia (current `main`, commit `0568d41`'s tree): `status::Union{Nothing,Bool}`
  (`true`=on), **no `commitment_mode` field at all**,
  `must_run::Union{Nothing,Bool} = false`.
- Python (`python/src/rts_gmlc_case/generation.py` lines ~196-217, read this
  session, not modified): `status=OperationalStates.ONLINE` (an enum),
  `commitment_mode=CommitmentModes.COMMITTED`, `must_run=False` — the *old*
  shape.

Julia's `main` is ahead of Python's `power_openapi_models` here. This was
confirmed independently by the coordinator before ruling on the fix. It does
**not** block this task's cross-language equivalence check (JE7 compares
component counts and time-series `data_hash` sets — both confirmed identical
above — not a full field-by-field JSON diff, per the original Julia tutorial
plan's Task 10 test shape). It **may** matter for any future full-structural
cross-language comparison task. Per RULE ZERO, `power-openapi-models` (the
Python package) was not touched and is out of scope regardless.

## Deliberate, reasoned divergences from the Python source (language-forced, not oversights)

- **`SidecarWriter.write_series!`'s tz-naive-timestamp rejection has no Julia
  equivalent.** Python's `DatetimeIndex` can be tz-naive at runtime, so
  `sidecar.py` has an explicit `if timestamps.tz is None: raise ValueError`
  check (with its own pinned test, `test_tz_naive_timestamps_raise`). Julia's
  `TimeZones.ZonedDateTime` type *always* carries an explicit `TimeZone` at
  the type level — there is no tz-naive `ZonedDateTime` to construct in the
  first place, so `write_series!`'s signature
  (`timestamps::Vector{ZonedDateTime}`) makes this whole error path
  structurally impossible rather than something to runtime-check. The
  "tz-aware non-UTC converts to the correct instant" behavior *is* ported
  (unconditional `astimezone.(timestamps, tz"UTC")`), with its own test.
- **One Python sidecar test not ported**:
  `test_write_failure_cleans_up_temp_file_and_propagates` monkeypatches
  `os.replace` to inject a failure after the temp file is genuinely written,
  to prove the `except BaseException: unlink; raise` cleanup path actually
  fires. Julia has no equivalent of `monkeypatch.setattr` for `Base.mv`
  without adding a mocking dependency (not one of the anticipated deps), so
  this one test was not ported. The cleanup code itself (`catch; rm(tmp_path;
  force=true); rethrow(); end`) is present and structurally mirrors Python's,
  just not independently exercised by an injected-failure test.

## Verification checklist (all satisfied)

- [x] `julia --project=. -e 'using RTSGMLCCase'` compiles clean, checked after
      every new file (not just at the end).
- [x] `julia --project=test test/runtests.jl` passes in full: **3659 passed, 0
      failed, 0 errored** (3m32.6s — the timeseries and build stages each run
      several full RTS-GMLC builds; this is expected, not a hang).
- [x] `data_hash([1.0, 2.0, 3.0])` cross-language literal match, verified
      directly and asserted in `test/test_sidecar.jl`.
- [x] Every association's `length` matches its source CSV's row count (checked
      per-association in `test_timeseries.jl` and `test_build.jl` against the
      real parquet row counts).
- [x] Association counts match the Python build's counts — verified two ways:
      (a) the pinned `EXPECTED_SERVICE_ASSOCIATIONS = 510` /
      `EXPECTED_TIME_SERIES_ASSOCIATIONS = 282` from `python/tests/test_build.py`,
      asserted in `test_build.jl`; (b) a direct real-build-vs-real-build
      comparison (table above), including the stronger `data_hash`-set
      equality check.
- [x] `read_case` round-trips: build, read back, re-validate, compare per-bucket
      counts *and* per-component JSON (`OpenAPI.to_json`) field-for-field —
      `test_build.jl::"round trip components match bucket by bucket"`.
- [x] Byte-determinism: two independent full builds into two temp dirs, `==`
      on `system.json`'s raw bytes — `test_build.jl::"build is byte deterministic"`.
- [x] JuliaFormatter: **no `.JuliaFormatter.toml` found** anywhere in
      `SchemasTutorials` (workspace root or `julia/RTSGMLCCase/`) — checked
      explicitly, skipped per the brief's own conditional ("if the project has
      a formatter config"). All new/changed files were hand-formatted to match
      the existing files' established style (4-space indent, one kwarg per
      line for multi-line constructor calls, `function ... end` with explicit
      `return`, no ternaries, no `isa` gates outside the one pre-existing
      `_is_present` helper which already used it before this task and was left
      alone).

## Nothing ambiguous remained unresolved

Both material ambiguities encountered (the `ThermalStandard` schema-drift
compile failure, and `generation.jl`'s thermal-only coverage) were surfaced to
the coordinator with full diagnostics before any fix was attempted, and both
were explicitly ruled on before I proceeded. No other point in this task
required a judgment call I wasn't confident the brief + actual Python source
already settled.
