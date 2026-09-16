# Task E4 — Demand requirement and its time series (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md`. Progress
ledger: `.claude/plans/2026-09-01-capacity-expansion-progress.md` — Tasks
E1-E3 are done; read their ledger entries before starting, especially the
"Ruling carried forward" note about `prime_mover_type`-style enum-default
bugs (this task's models don't have that field, but the same "never rely
on a field default without checking" caution applies generally).

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`julia/`. Do not modify any file under `python/src/rts_gmlc_case/` other
than the new files below — this task needs no changes to existing
operations or investments modules, only new reads of two already-public
functions (see below). If you find you need to edit an existing file,
stop and report NEEDS_CONTEXT.

## What earlier tasks already gave you

- `investments/topology.py`: `InvestmentTopologyIndex.zone_id_by_name:
  dict[str, int]` — E1 named zones `"1"`, `"2"`, `"3"` (the 3 RTS areas).
- `investments/data.py`: `investments_source_dir() -> Path`.
- `rts_gmlc_case/timeseries.py` (operations, **do not modify**) — reuse
  two of its already-public pieces directly, no private-name imports
  needed this time:
  - `RESOLUTION_BY_SIMULATION: dict[str, tuple[str, pd.Timedelta]]` —
    use `RESOLUTION_BY_SIMULATION["DAY_AHEAD"]` to get `("PT1H",
    pd.Timedelta(hours=1))`. The plan's "reuse ... including `PT1H`"
    instruction means literally this constant, not a re-derivation.
  - `read_profile(csv_path: Path, column: str | None, resolution:
    pd.Timedelta) -> tuple[pd.DatetimeIndex, np.ndarray]` — handles the
    Layout A CSV shape (`Year,Month,Day,Period,<col1>,<col2>,...`)
    generically. The data file this task reads (below) is Layout A with
    a `Period` column, so this function works unmodified — pass the zone
    name string as `column`.
- `rts_gmlc_case/sidecar.py` — `SidecarWriter` (unchanged contract: same
  content-addressed parquet files, same `data_hash`). Construct one with
  the same `case_dir` the rest of the build uses (Task E6's driver will
  pass it in — for this task's own tests, construct one against a
  `tmp_path`).

## Data

`data/RTS-investments/loaddata/RTS_DA_regional_load.csv` (under
`investments_source_dir()`), verified by the controller: `8785` lines
(8784 data rows = 366 days x 24 hours, 2020 is a leap year), columns
`Year,Month,Day,Period,1,2,3` — **the three load columns are named `"1"`,
`"2"`, `"3"`, matching E1's zone names exactly.** This is Layout A
(`Period` column present), one row per hour, values in MW.

```
Year,Month,Day,Period,1,2,3
2020,1,1,1,985.0197922,1102.675901,1249.636191
2020,1,1,2,985.7248887,1082.937195,1192.383739
```

## New files

- `python/src/rts_gmlc_case/investments/demand.py`
- `python/tests/test_investments_demand.py`

## What to build

### `add_demand_requirements(doc, source, sidecar, inv_idx) -> dict[str, int]`

- `source` = `investments_source_dir()`'s return.
- `sidecar` = a `SidecarWriter` instance (constructed by the caller —
  Task E6's driver — against the case's real output directory; this
  task's own tests construct one against `tmp_path`).
- `inv_idx` = E1's `InvestmentTopologyIndex`.
- For each zone name in sorted order (`"1"`, `"2"`, `"3"` — same
  determinism convention every earlier stage used):
  - Read the column via `timeseries.read_profile(csv_path, column=zone_name,
    resolution=pd.Timedelta(hours=1))` (the CSV path is
    `source / "loaddata" / "RTS_DA_regional_load.csv"`, `resolution` from
    `RESOLUTION_BY_SIMULATION["DAY_AHEAD"][1]`).
  - Write the values through `sidecar.write(timestamps, values)` ->
    `(uri, data_hash)`, exactly like the operations `attach_time_series`
    does.
  - Build one `DemandRequirement`
    (`power_openapi_models.investments.models.DemandRequirement`):
    - `power_systems_type = "PowerLoad"` — the operations campaign's
      `rts_gmlc_case.demand` module builds loads as `PowerLoad`
      components (confirmed: read its module docstring / imports), and
      R39's "exact PSY type name this campaign emits" principle extends
      naturally to the load side even though R39's own quote only lists
      the 4 generation types. If you think this is wrong, say so in your
      report rather than silently picking something else.
    - `region = [inv_idx.zone_id_by_name[zone_name]]`.
    - `conformity = "UNDEFINED"` (the schema's own default — matches the
      operations `PowerLoad` convention of the same name; leave it at
      the default rather than inventing a different value).
    - `value_of_lost_load` — **required, and the plan calls it
      "unsourced -> external, labelled".** Pick a standard illustrative
      VOLL figure (a commonly-cited default is in the $9,000-10,000/MWh
      range) and label it as illustrative in a code comment, the same
      honesty framing `investments/costs.py` already uses. **Note for
      your report, don't silently act on it:** the controller separately
      found `scalars.csv` has a `cost_dropped_load,10000,--2004$ per
      MWh-- cost of dropped load (only allowed in historical years)` row
      — numerically close to a plausible VOLL, but the plan explicitly
      classifies this field as unsourced, and the "(only allowed in
      historical years)" caveat suggests the original campaign
      deliberately did not treat it as a general-purpose sourced VOLL.
      Follow the plan's explicit classification (illustrative/external),
      but if your illustrative number happens to land near 10000, say in
      the report that this is coincidence/plausibility, not a citation
      of `scalars.csv`.
    - Everything else left at schema defaults (`new_demand_mw=0.0`,
      `growth_rate=0.0`, `new_construction_year=2020`,
      `unserved_demand_curve=None`, `requirements=[]`) — none of this
      task's inputs populate them and nothing in the plan asks you to.
  - `doc.add_component(demand_requirement)`.
  - Build one `SingleTimeSeries` association
    (`power_openapi_models.timeseries.models.SingleTimeSeries` +
    `TimeSeriesAssociation`), field-for-field matching the shape
    `rts_gmlc_case/timeseries.py`'s `attach_time_series` already builds
    (read that function in full before writing this one — same import
    names, same field set):
    - `association_id=doc.next_id()`
    - `owner_id=<the DemandRequirement's id>`
    - `owner_type="DemandRequirement"`
    - `owner_category=OwnerCategory.Component`
    - `time_series_type="SingleTimeSeries"`
    - `name="requirement"` (matches the operations
      `PARAMETER_TARGETS["Requirement"]` target name for the same
      quantity)
    - `features={}`
    - `uri=<from sidecar.write>`
    - `data_hash=<from sidecar.write>`
    - `element_type="f64"`
    - `element_shape=[]`
    - `array_shape=[len(values)]`
    - `units="MW"`
    - `quantity_kind="requirement"`
    - `unit_system="NATURAL_UNITS"`
    - `time_reference="zoneless"`
    - `initial_timestamp=timestamps[0]`
    - `resolution="PT1H"`
    - `length=len(values)`
  - Append via `doc.document.time_series_associations.append(TimeSeriesAssociation(association))`
    — same wrapping the operations stage uses.
- Return `{zone_name: demand_requirement_id}` (or whatever shape is
  natural; your call, but later tasks may want a zone-name -> id map).

## Verify

- Exactly 3 `DemandRequirement` components, one per zone, `region` each a
  single-element list resolving to a real zone id.
- Exactly 3 new `time_series_associations` rows, one per
  `DemandRequirement`, `resolution == "PT1H"`.
- Each association's `length` equals `8784` (the CSV's row count) —
  assert against a fresh CSV read, not the hardcoded number.
- Each `uri` points to a parquet file that actually exists under
  `sidecar`'s `timeseries/` directory, and re-reading it reproduces the
  same values (round-trip sanity, mirroring how the operations
  timeseries tests already check this — look at the operations
  timeseries test file for the pattern).
- Every `data_hash` matches `rts_gmlc_case.sidecar.data_hash(values)`
  computed independently in the test (not just trusted from the write
  call).
- `doc.validate()` still passes.

## Report

Write your full report to
`.claude/plans/task-E4-report.md`. Run
`cd python && uv run pytest tests/test_investments_demand.py -v`, then
`uv run pytest -m "not slow"` for the full non-slow suite (this task's
own tests read one real 8784-row CSV and write real parquet files —
if that makes your new tests noticeably slower than the rest of the
non-slow suite, say so in the report, but don't mark them `slow` unless
they're genuinely comparable to the operations full-case-build tests
that already carry that marker), then `uv run pytest -m "not slow" -W
error::UserWarning -q`. Reply with only DONE / DONE_WITH_CONCERNS /
NEEDS_CONTEXT / BLOCKED, the exact commands and pass counts, and a
one-line pointer to the report file.

State clearly in the report: the exact `value_of_lost_load` figure you
picked, confirmation that `power_systems_type="PowerLoad"` was checked
against the operations `demand.py` code (not assumed), and your test
runtime if it's a meaningfully larger contributor to the non-slow suite's
total time than the other tasks' tests have been.

If anything here is ambiguous in a way that's load-bearing for Task E6
(the combined-document build) or Task JE (the Julia mirror, which will
need the same association shape to match byte-for-byte per R19/data_hash
parity), ask before guessing rather than after.