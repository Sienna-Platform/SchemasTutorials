# Task E1 — Dataset module, nodes, zones, topology mapping (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md` (read its
"Global constraints" and "What the dataset does and does not support"
sections — they bind on every task, not just this one). Progress ledger:
`.claude/plans/2026-09-01-capacity-expansion-progress.md`.

**Do not run `git add`, `git commit`, or any git write. Leave the working
tree unstaged.** Do not modify anything under
`python/src/rts_gmlc_case/` (the existing operations code) except the one
addition to `document.py` specified below. Do not touch `julia/` at all.

## What already exists (read before writing anything)

- `python/src/rts_gmlc_case/data.py` — the operations dataset module.
  `rts_source_dir()` does a pinned, checksum-verified download with an
  atomic extract-to-staging-then-rename, and an all-required-files-present
  cache check (`_missing_entries`) that refuses to silently redownload
  over an existing-but-incomplete directory. Mirror this file's shape and
  error messages for the new `investments` dataset module, with one
  deliberate difference (see "Dataset source" below): **the investments
  data already exists locally** at `data/RTS-investments/` (repo root,
  4 levels up from this new module — same `REPO_ROOT` convention as
  `data.py`), so there is no verified pinned URL/checksum for it in this
  session. Do not invent one. Instead: validate that the 16 required
  files are present (list below) exactly the way `_missing_entries` does,
  and raise a `RuntimeError` naming every missing path if any are absent.
  If the directory doesn't exist at all, raise `RuntimeError` telling the
  user to place the dataset there — do not attempt any download. Leave a
  short comment at the top of the new `data.py` noting that the pinned
  download step is not wired up because no verified upstream URL was
  available this session (a future session can add it the same way the
  operations `data.py` does, once someone identifies the authoritative
  source).
- `python/src/rts_gmlc_case/topology.py` — style to mirror: module
  docstring stating the mapping decisions and citing rulings; a
  `@dataclass` index type returned to later stages; sorted-order id
  minting for determinism; `doc.next_id()` / `doc.add_component(model)`
  from `CaseDocument`; explicit `ValueError` on any unmapped key, never a
  silent skip.
- `python/src/rts_gmlc_case/document.py` — `CaseDocument`. Read this
  fully. `add_component` buckets a component's `model_dump(mode="json",
  by_alias=True)` dict under `type(model).__name__` in
  `document.components` and returns its id. There is currently no
  equivalent for **supplemental attributes** — you must add one:

  ```python
  def add_supplemental_attribute(
      self, model: BaseModel, *, component_id: int, component_type: str
  ) -> int:
      """Add a supplemental attribute describing one component. Mints the
      attribute's id, appends the dumped model to
      ``document.supplemental_attributes``, appends a matching
      ``SupplementalAttributeAssociation`` row, and returns the minted id.
      """
  ```

  Import `SupplementalAttributeAssociation` from
  `power_openapi_models.infrastructure_core.models` (already imported in
  `document.py` inside a `try/except ImportError` for the same class —
  reuse that name, don't re-import). Field names on
  `SupplementalAttributeAssociation`: `component_id: int`,
  `component_type: str`, `attribute_id: int`, `attribute_type: str`. Set
  `attribute_type=type(model).__name__`. Append the row to
  `self.document.supplemental_attribute_associations`. This helper has no
  existing caller — add a focused unit test for it directly (e.g. a tiny
  dummy attribute round-tripped through `CaseDocument`), separate from the
  topology tests.
- `python/tests/test_topology.py` — test style to mirror: read the source
  CSV directly in the test and assert derived counts/values against it
  (not against hardcoded numbers alone), plus one block of pinned
  "Expected component counts" asserted as a sanity check.
- `python/pyproject.toml` — `pytest` marker `slow` exists
  (`-m "not slow"` deselects it). This task's tests are fast (no full
  case build) — do not mark them slow.

## New files

- `python/src/rts_gmlc_case/investments/__init__.py` (empty or minimal)
- `python/src/rts_gmlc_case/investments/data.py`
- `python/src/rts_gmlc_case/investments/topology.py`
- `python/tests/test_investments_data.py`
- `python/tests/test_investments_topology.py`
- (extend, don't move) `python/src/rts_gmlc_case/document.py` — add
  `add_supplemental_attribute` above
- (extend) `python/tests/test_document.py` — add the round-trip test for
  it, or a new `test_document_supplemental_attribute.py` if that reads
  cleaner

## Dataset source

Root: `data/RTS-investments/` (already present in this checkout — verify,
don't fetch). Required files (the "16-file subset" the plan refers to):

```
hierarchy_rts.csv
scalars.csv
capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv
capacitydata/upv_exog_cap_reference_nodal.csv
capacitydata/wind-ons_exog_cap_reference_nodal.csv
financials/reg_cap_cost_mult_nodal_rts.csv
loaddata/RTS_DA_regional_load.csv
storagedata/storage_duration_pshdata.csv
storagedata/storinmaxfrac.csv
supplycurvedata/hyd_add_upg_cap.csv
supplycurvedata/upv_supply_curve-reference_nodal.csv
supplycurvedata/wind-ons_supply_curve-reference_nodal.csv
transmission/transmission_capacity_init_AC_rts_nodal.csv
transmission/transmission_capacity_init_nonAC_nodal.csv
transmission/transmission_distance_cost_500kVac_nodal.csv
transmission/transmission_distance_cost_500kVdc_nodal.csv
```

Confirm this list against what's actually on disk under
`data/RTS-investments/` (run `find`/`ls` yourself) before hardcoding it —
if the directory holds exactly these 16 and no more, that confirms the
"16-file subset" framing; note in your report if it doesn't match so the
controller can adjust the plan's framing.

Do **not** reference or require `rts_psy5.sqlite` or `RTS_load_hourly.h5`
even if present nearby — the plan explicitly excludes them from this
dataset module.

Also needed for this task (already downloaded, from the **operations**
dataset, reuse `rts_gmlc_case.data.rts_source_dir()`):
`SourceData/bus.csv`, which has `Bus ID`, `Bus Name`, `Area`, `Zone`
columns (see `topology.py` for how it's already read).

`hierarchy_rts.csv`'s first column (`*nodal`) has values like `b101` —
strip the leading `b` to get the numeric bus id joining to `bus.csv`'s
`Bus ID`. Its `ba` column (5 ReEDS balancing areas) is present but must be
**unused** for this task per the ruling below.

## What to build

### `investments_source_dir() -> Path`

Returns `data/RTS-investments/` after validating all 16 files are
present (per "Dataset source" above). No download.

### `add_investment_topology(doc, source, idx) -> InvestmentTopologyIndex`

- `source` is the path returned by `investments_source_dir()`.
- `idx` is the `TopologyIndex` already returned by the operations
  `add_topology` (import `rts_gmlc_case.topology.TopologyIndex` as the
  parameter's type) — reuse it to relate `Node` ids to `ACBus` ids; do not
  re-read `bus.csv` through a second code path if you can get what you
  need from `idx` plus the same `SourceData/bus.csv` read the operations
  stage already does (read it again here if needed for `Area`/`Zone`
  columns — `TopologyIndex` doesn't carry the raw dataframe).
- **`Node`** (`power_openapi_models.investments.models.Node`; fields:
  `id: int`, `name: str`, `bus_type: ACBusType | None = "PQ"`): one Node
  per bus in `bus.csv` (73 total). Use the same `name` as the
  corresponding `ACBus`'s name (bus name, e.g. `"Abel"`), and set
  `bus_type` from the same `_normalize_bustype`-equivalent conversion
  `topology.py` already does for `ACBus.bustype` (import and reuse that
  function rather than duplicating its logic — export it if it isn't
  already, or add a tiny local equivalent if reuse isn't clean; use your
  judgment and say which you chose in your report).
- **`Zone`** (`power_openapi_models.investments.models.Zone`; fields:
  `id: int`, `name: str`): **R38 — one Zone per RTS *Area* (3 total: "1",
  "2", "3"), not per the dataset's `Zone` column (21) and not per
  `hierarchy_rts.csv`'s `ba` column (5 ReEDS balancing areas).** Name each
  Zone the same string as the corresponding operations `Area.name` (so
  `"1"`, `"2"`, `"3"`), added in sorted order for deterministic ids.
  **Add an explicit test asserting there are exactly 3 zones and that the
  5-BA structure was NOT what got emitted** (e.g. assert the zone names
  are `{"1", "2", "3"}`, not 5 ReEDS BA codes like `p28`).
- **`TopologyMapping`** (`power_openapi_models.investments.models.TopologyMapping`;
  fields: `id: int`, `buses: list[str] | None`) — **this is a
  supplemental attribute, not a bucketed component** (per
  `SiennaSchemas/Investments/Attributes/TopologyMapping.json`'s
  description: "Supplemental attribute storing the mapping between a zone
  and the associated buses"). One `TopologyMapping` per Zone, `buses` =
  the list of bus **names** (not numbers) whose `Area` equals that zone's
  name, added via the new `CaseDocument.add_supplemental_attribute(...,
  component_id=<the Zone's id>, component_type="Zone")`.

### `InvestmentTopologyIndex` (new `@dataclass`, mirrors `TopologyIndex`'s shape)

Fields your later tasks (E2+) will need — at minimum:
`node_id_by_bus_number: dict[int, int]`, `zone_id_by_name: dict[str, int]`.
Add whatever else is naturally produced (e.g. a reverse lookup) but don't
speculatively build fields nothing in this task or the plan's later task
descriptions calls for.

## Verify (from the plan; also your own acceptance bar)

- 73 `Node` components, 3 `Zone` components.
- Every `Node` maps to exactly one bus (`node_id_by_bus_number` covers all
  73 bus numbers, no duplicates).
- Every bus appears in exactly one `TopologyMapping.buses` list across the
  3 zones (partition, not overlap, not omission).
- `doc.validate()` passes after this stage (no dangling references) —
  note `add_supplemental_attribute` doesn't currently get checked by
  `validate()`'s reference-resolution pass since supplemental attributes
  aren't in `_REFERENCE_FIELDS`; that's fine, don't extend `validate()` in
  this task unless a later task in the plan explicitly asks for it.
- Zone names are exactly `{"1", "2", "3"}`.

## Report

Run tests with `cd python && uv run pytest tests/test_investments_data.py
tests/test_investments_topology.py tests/test_document.py -v` (adjust
paths if you named the document test file differently) plus the full
non-slow suite (`uv run pytest -m "not slow"`) to confirm no regression
in the operations tests. Report DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT
/ BLOCKED, the exact test commands run and their pass counts, which
design choices you made where this brief left judgment to you (the
bustype-normalizer reuse question above, and anything else), and any
mismatch between the assumed 16-file list and what's actually on disk.
