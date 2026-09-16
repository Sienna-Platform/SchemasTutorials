# Task E4 report — demand requirement and its time series (Python)

## Files

- New: `python/src/rts_gmlc_case/investments/demand.py`
  (`add_demand_requirements`, `LOAD_DATA_FILE`, `VALUE_OF_LOST_LOAD`).
- New: `python/tests/test_investments_demand.py` (5 tests).
- No existing file under `python/src/rts_gmlc_case/` was modified. Only
  reads of `investments/topology.py` (`InvestmentTopologyIndex`),
  `investments/data.py` (`investments_source_dir`), `timeseries.py`
  (`RESOLUTION_BY_SIMULATION`, `read_profile`), and `sidecar.py`
  (`SidecarWriter`, `data_hash`) as instructed.
- No git write (`add`/`commit`) was run; working tree is unstaged except
  for these two new files (untracked). `julia/` untouched.

## What was built

`add_demand_requirements(doc, source, sidecar, inv_idx) -> dict[str, int]`
iterates the 3 zone names in sorted (`key=int`) order — `"1"`, `"2"`,
`"3"` — and for each:

- Reads the zone's load column from
  `source/loaddata/RTS_DA_regional_load.csv` via
  `timeseries.read_profile(csv_path, column=zone_name,
  resolution=RESOLUTION_BY_SIMULATION["DAY_AHEAD"][1])` (`PT1H`), unmodified
  and reused directly.
- Writes the values through `sidecar.write(timestamps, values)`.
- Builds one `DemandRequirement`: `power_systems_type="PowerLoad"`,
  `region=[inv_idx.zone_id_by_name[zone_name]]`, `conformity` left at the
  schema default (`"UNDEFINED"`), `value_of_lost_load=VALUE_OF_LOST_LOAD`,
  everything else (`new_demand_mw`, `growth_rate`,
  `new_construction_year`, `unserved_demand_curve`, `requirements`) left
  at schema defaults. `name=zone_name` (not specified verbatim in the
  brief; chosen to mirror the `Zone.name`/`SupplyTechnology.name`
  convention every earlier stage used for its own natural key).
- Builds one `SingleTimeSeries` + `TimeSeriesAssociation`, field-for-field
  matching `attach_time_series`'s shape exactly as specified in the brief
  (`owner_type="DemandRequirement"`, `name="requirement"`,
  `quantity_kind="requirement"`, `units="MW"`, `unit_system=
  "NATURAL_UNITS"`, `time_reference="zoneless"`, `element_type="f64"`,
  `resolution="PT1H"`, etc.).
- Returns `{zone_name: demand_requirement_id}`.

No `prime_mover_type`-style enum-default field exists on `DemandRequirement`
(confirmed by reading the model in
`power-openapi-models/src/power_openapi_models/investments/models.py`), so
the carried-forward ruling about explicit enum defaults does not apply
here — nothing was left at a risky implicit default.

## `value_of_lost_load`

**Picked `9_000.0` USD/MWh**, labelled illustrative in a code comment in
`demand.py`, per the plan's "unsourced -> external, labelled" instruction.
This is a commonly-cited illustrative VOLL figure for this kind of
worked example, not derived from any file in this dataset.

The controller separately found `scalars.csv`'s
`cost_dropped_load,10000,--2004$ per MWh-- cost of dropped load (only
allowed in historical years)` row. My chosen figure (9,000) is close in
order of magnitude to that row but was picked independently — it is
**not** a citation of `scalars.csv`, consistent with the plan's explicit
classification of `value_of_lost_load` as unsourced/external and that
row's "(only allowed in historical years)" caveat. Flagging explicitly
per the brief's instruction, since 9,000 sits in the same $9,000–10,000
illustrative band the brief itself cites.

## `power_systems_type = "PowerLoad"` verification

Confirmed by reading `python/src/rts_gmlc_case/demand.py` in full (not
assumed): its module docstring says "Demand-side stage: loads, ...", and
`add_loads` builds `PowerLoad(...)` for every bus with nonzero `MW Load`
(imported from `power_openapi_models.operations.models`). This extends
R39's "exact PSY type name this campaign emits" principle from the
generation side (E2's `SupplyTechnology.power_systems_type`) to the
demand side, as the brief anticipated. I did not find anything to
contradict this reading; no report of a discrepancy is needed here.

## Verify section — results

- Exactly 3 `DemandRequirement` components, one per zone name (`"1"`,
  `"2"`, `"3"`), each `region` a single-element list resolving to a real
  zone id from `inv_idx.zone_id_by_name`. Confirmed.
- Exactly 3 new `time_series_associations` rows (`owner_type ==
  "DemandRequirement"`), each `resolution == "PT1H"`. Confirmed.
- Each association's `length` checked against a **fresh** CSV read
  (`pd.read_csv(inv_src / LOAD_DATA_FILE)`, not the hardcoded literal):
  `len(raw) == 8784`, and every association's `length` equals that.
  Confirmed.
- Each `uri` resolves to a parquet file that exists under
  `tmp_path/timeseries/`; re-reading it via `pyarrow.parquet.read_table`
  reproduces the same values as a fresh read of the CSV's own zone
  column. Confirmed (`test_uri_exists_and_round_trips_and_data_hash_matches`).
- Every `data_hash` checked against
  `rts_gmlc_case.sidecar.data_hash(values)` computed independently from a
  freshly-read CSV column in the test (not trusted from the write call).
  Confirmed, same test.
- `doc.validate()` passes (`test_validate_passes`).

## Test commands and results

```
cd python && uv run pytest tests/test_investments_demand.py -v
```
5 passed in 0.64s.

```
uv run pytest -m "not slow" -q
```
110 passed, 5 deselected in 13.81s (was 105 passed after E3; +5 new, no
regressions).

```
uv run pytest -m "not slow" -W error::UserWarning -q
```
110 passed, 5 deselected in 13.71s — no `UserWarning`s raised.

## Runtime note

The new tests' own runtime is 0.64s for 5 tests, well within the noise of
the 13.7s full non-slow suite (about 4-5% of total, similar order to
other tasks' investments tests — not a meaningfully larger contributor).
The CSV read is cached process-wide via `timeseries._load_csv`'s
`lru_cache`, so re-reading the same 8784-row file 3 times per test (once
per zone, across 5 tests) is cheap; no `slow` marker needed.

## Ambiguities encountered

None load-bearing enough to stop and ask. The one open judgment call
(`DemandRequirement.name`) is documented above and is a low-cost-if-wrong
choice: later tasks (E6, JE) consume `add_demand_requirements`'s returned
`dict[str, int]` (zone name -> id) rather than the `name` field itself,
per the brief's own "or whatever shape is natural" allowance for the
return value.

## Status: DONE
