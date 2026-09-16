# Python RTS OpenAPI Case Tutorial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python project + markdown tutorial that builds RTS-GMLC into an OpenAPI case document (`system.json` + parquet `timeseries/` sidecar) using only `power-openapi-models`, pandas, and pyarrow.

**Architecture:** A `rts_gmlc_case` package with one module per build stage (topology, branches, generation, loads/reserves, time series), a hand-written `document.py` container mirroring the Julia `SystemDocument` JSON tree, and a `build_rts.py` driver. Tutorial chapters in `docs/` narrate each module.

**Tech Stack:** Python ≥3.11, uv, pydantic v2 via `power-openapi-models` (editable path dep `../../power-openapi-models`), pandas, pyarrow, pytest.

**Spec:** `.claude/plans/2026-08-28-openapi-rts-tutorials-design.md`

## Global Constraints

- No Sienna reference anywhere except the package name `power-openapi-models`: no IS/PSY/PTDP imports, no Sienna URLs in tutorial prose, no HDF5.
- Natural units: document `unit_system = "NATURAL_UNITS"`; MW/MVAR/MVA/kV as in source; branch r/x/b per-unit on `base_power = 100.0`; angles radians.
- Sidecar contract exactly as the design doc states: `timeseries/ts_<hash16>.parquet`, columns `timestamp` (ms, UTC) + `value` (float64), `data_hash` = SHA-256 of float64-LE bytes, `uri = "timeseries/ts_<hash16>.parquet"`, `time_series_storage_file = "timeseries"`.
- Deterministic build: iterate CSVs in file order; mint ids in stage order (topology → branches → generation → loads/storage → reserves → time series).
- Generated model fields are authoritative; PTDP's `data/rts.json` is a dev-only value reference. When a field name is in doubt, read `power_openapi_models/{core,operations,timeseries}/models.py`.
- `python3` always; run `uv run pytest` from `python/` after every task.
- **Git policy:** leave all changes unstaged for user review (`git add -N` for new files only). Never commit or push; the user commits. Where this plan says "Checkpoint", stop and report, do not `git commit`.

---

### Task 1: Project scaffold + pinned data download

**Files:**
- Create: `python/pyproject.toml`, `python/src/rts_gmlc_case/__init__.py`, `python/src/rts_gmlc_case/data.py`, `python/tests/test_data.py`, `python/README.md`, `.gitignore` (repo root: add `cases/`, `data/`, `.venv/`)

**Interfaces:**
- Produces: `data.rts_source_dir() -> Path` — downloads/caches the RTS-GMLC v0.2.2 tarball into `<repo-root>/data/RTS-GMLC/`, verifies sha256, returns the `RTS_Data` directory. `data.SOURCE_DATA` / `data.TIMESERIES_DATA` subpath helpers.

- [ ] **Step 1: scaffold** — `cd python && uv init --lib --name rts-gmlc-case`, then set `requires-python = ">=3.11"`, add deps: `uv add pandas pyarrow pydantic && uv add --editable ../../power-openapi-models && uv add --dev pytest`. (Path dep note in README: consumers outside this workspace `pip install power-openapi-models`.)
- [ ] **Step 2: failing test**

```python
# tests/test_data.py
from pathlib import Path
from rts_gmlc_case import data

def test_source_dir_exists_and_has_tables():
    src = data.rts_source_dir()
    for name in ("bus.csv", "branch.csv", "gen.csv", "reserves.csv", "timeseries_pointers.csv"):
        assert (src / "SourceData" / name).is_file()
```

- [ ] **Step 3: implement `data.py`** — stdlib only:

```python
import hashlib, tarfile, urllib.request
from pathlib import Path

URL = "https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz"
SHA256 = "f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2"
REPO_ROOT = Path(__file__).resolve().parents[3]

def rts_source_dir() -> Path:
    root = REPO_ROOT / "data" / "RTS-GMLC"
    marker = root / "RTS_Data" / "SourceData" / "bus.csv"
    if not marker.is_file():
        root.mkdir(parents=True, exist_ok=True)
        tar_path = root / "rts.tar.gz"
        urllib.request.urlretrieve(URL, tar_path)
        digest = hashlib.sha256(tar_path.read_bytes()).hexdigest()
        if digest != SHA256:
            raise RuntimeError(f"checksum mismatch for {URL}: {digest}")
        with tarfile.open(tar_path) as tf:
            tf.extractall(root, filter="data")
        # flatten RTS-GMLC-0.2.2/ into root
        inner = next(root.glob("RTS-GMLC-*"))
        for child in inner.iterdir():
            child.rename(root / child.name)
        inner.rmdir(); tar_path.unlink()
    return root / "RTS_Data"
```

- [ ] **Step 4: run** — `uv run pytest tests/test_data.py -v` → PASS (network on first run only).
- [ ] **Step 5: Checkpoint** — report; leave unstaged (`git add -N` new files).

---

### Task 2: The document container (`document.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/document.py`, `python/tests/test_document.py`

**Interfaces:**
- Produces: `SystemDocument(base_power: float)` with fields `unit_system="NATURAL_UNITS"`, `components: dict[str, list[BaseModel]]`, `time_series_associations: list`, `service_associations: list`, `supplemental_attributes: list`, `supplemental_attribute_associations: list`, `ext: dict[int, dict]`, `time_series_storage_file: str | None`. Methods: `next_id() -> int`, `add_component(model) -> int` (asserts `model.id` set, buckets by `type(model).__name__`), `to_tree() -> dict`, `write(path)`, `validate()` (unique ids; every integer reference field among {`bus`, `arc`, `area`, `load_zone`, `circuit`, `from_id`, `to_id`, `owner_id`} resolves), `read(path) -> dict` (raw tree; typed re-parse happens in Task 9).

**Critical:** before writing `to_tree`, read `PowerOpenAPIModels.jl/src/document.jl:563-630` (`document_tree`, `write_document`) at `/Users/jdlara/cache/psy6/PowerOpenAPIModels/` and copy the exact key set, optional-key omission rules, and JSON layout. The Julia package defines the wire format; this module follows it. Record the key list in the module docstring.

- [ ] **Step 1: failing test**

```python
# tests/test_document.py
import pytest
from power_openapi_models.operations.models import Area
from rts_gmlc_case.document import SystemDocument

def test_add_and_tree_roundtrip(tmp_path):
    doc = SystemDocument(base_power=100.0)
    area = Area(id=doc.next_id(), name="1", peak_active_power=0.0, peak_reactive_power=0.0)
    doc.add_component(area)
    doc.validate()
    tree = doc.to_tree()
    assert tree["base_power"] == 100.0
    assert tree["unit_system"] == "NATURAL_UNITS"
    assert [c["name"] for c in tree["components"]["Area"]] == ["1"]
    doc.write(tmp_path / "system.json")
    assert (tmp_path / "system.json").is_file()

def test_dangling_reference_rejected():
    from power_openapi_models.operations.models import Arc
    doc = SystemDocument(base_power=100.0)
    doc.add_component(Arc(id=doc.next_id(), from_id=999, to_id=998))
    with pytest.raises(ValueError, match="unresolved"):
        doc.validate()
```

(Adjust the `Area` constructor to the generated model's actual required fields — check `operations/models.py` first; same for `Arc`.)

- [ ] **Step 2: run** — expect FAIL (module missing).
- [ ] **Step 3: implement** — plain class (not pydantic) holding pydantic models; serialize each with `model_dump(mode="json", exclude_none=True)`; `write` uses `json.dumps(tree, indent=1, sort_keys=True)`.
- [ ] **Step 4: run to PASS.** Checkpoint.

---

### Task 3: Topology — areas, zones, buses (`topology.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/topology.py`, `python/tests/test_topology.py`

**Interfaces:**
- Produces: `add_topology(doc: SystemDocument, source: Path) -> TopologyIndex` where `TopologyIndex` is a dataclass with `bus_id_by_number: dict[int, int]`, `area_id_by_name: dict[str, int]`, `zone_id_by_name: dict[str, int]`.

Mapping (from `SourceData/bus.csv`): one `Area` per distinct `Area` value, one `LoadZone` per distinct `Zone` value (both stringified names, added in sorted order), then per row one `ACBus`: `number=Bus ID`, `name=Bus Name`, `base_voltage=BaseKV`, `bustype=Bus Type` normalized (`Ref` → `"REF"`, else uppercase — confirm the `ACBusType` enum members in `core/models.py`), `magnitude=V Mag`, `angle=radians(V Angle)`, `voltage_limits={"min":0.95,"max":1.05}`, `area`/`load_zone` = mapped ids, `available=True`. Raise `ValueError` if `MW Shunt G` or `MVAR Shunt B` is nonzero (RTS has none; fail loudly rather than drop data).

- [ ] **Step 1: failing test** — small literal CSV fixture written to `tmp_path` (3 buses, 2 areas, 1 zone) + the real file:

```python
def test_topology_counts_from_source():
    doc = SystemDocument(base_power=100.0)
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    bus = pd.read_csv(src / "bus.csv")
    assert len(doc.components["ACBus"]) == len(bus)
    assert len(doc.components["Area"]) == bus["Area"].nunique()
    assert len(doc.components["LoadZone"]) == bus["Zone"].nunique()
    abel = next(c for c in doc.components["ACBus"] if c.number == 101)
    assert abel.name == "Abel" and abs(abel.angle - math.radians(bus.loc[bus["Bus ID"]==101,"V Angle"].iloc[0])) < 1e-12
```

- [ ] **Step 2–4:** run FAIL → implement → PASS. Checkpoint.

---

### Task 4: Branches — arcs, lines, transformers, HVDC (`branches.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/branches.py`, `python/tests/test_branches.py`

**Interfaces:**
- Consumes: `TopologyIndex` from Task 3.
- Produces: `add_branches(doc, source, idx) -> None`; internal `arc_id(doc, idx, cache, from_bus, to_bus) -> int` reusing one `Arc` per (from,to) pair.

Mapping (`branch.csv`): `Tr Ratio == 0` → `Line` with `r=R`, `x=X`, `b={"from": B/2, "to": B/2}`, `g={"from":0,"to":0}`, `base_power=100.0`, `rating=Cont Rating`, `rating_b=LTE Rating`, `rating_c=STE Rating`, `angle_limits={"min":-3.1416,"max":3.1416}`, flows 0.0, `name=UID`. `Tr Ratio != 0` → one `TransformerCircuit` (`arc`, `tap=Tr Ratio`, `alpha=0.0`, `r`, `x`, `control_objective="FIXED"`, ratings as above, `control_limits={"min":0.9,"max":1.1}`) plus one `TwoWindingTransformer` (`name=UID`, `circuit=<circuit id>`, `magnetizing_shunt={"real":0,"imag":0}`, `shunt_location="PRIMARY"`) — confirm exact required fields against `operations/models.py` and value conventions against `TransformerCircuit`/`TwoWindingTransformer` entries in `/Users/jdlara/cache/psy6/PowerTableDataParser.jl/data/rts.json`. `dc_branch.csv` → one `TwoTerminalGenericHVDCLine` (single row; map `From Bus`/`To Bus` through a fresh arc, ratings from `MW Load`).

- [ ] **Step 1: failing test**

```python
def test_branch_partition_and_arcs():
    doc = SystemDocument(base_power=100.0)
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    add_branches(doc, src, idx)
    br = pd.read_csv(src / "branch.csv")
    n_xf = (br["Tr Ratio"] != 0).sum()
    assert len(doc.components["Line"]) == len(br) - n_xf
    assert len(doc.components["TwoWindingTransformer"]) == n_xf
    assert len(doc.components["TransformerCircuit"]) == n_xf
    pairs = {(a.from_id, a.to_id) for a in doc.components["Arc"]}
    assert len(pairs) == len(doc.components["Arc"])  # deduplicated
    doc.validate()
```

- [ ] **Step 2–4:** FAIL → implement → PASS. Add dev-only spot-check test guarded by the reference file's existence: line "A1" has `r=0.003, x=0.014, b.from=0.2305, rating=175.0`. Checkpoint.

---

### Task 5: Generators and operation costs (`generation.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/generation.py`, `python/tests/test_generation.py`

**Interfaces:**
- Consumes: `TopologyIndex`.
- Produces: `add_generation(doc, source, idx) -> dict[str, int]` (generator id by `GEN UID`); internal `thermal_cost(row) -> ThermalGenerationCost`, `unit_type_target(unit_type) -> str`.

Type mapping (module-level dict, the tutorial's centerpiece table):

```python
UNIT_TYPE_TO_MODEL = {
    "NUCLEAR": "ThermalStandard", "STEAM": "ThermalStandard",
    "CT": "ThermalStandard", "CC": "ThermalStandard",
    "WIND": "RenewableDispatch", "PV": "RenewableDispatch", "CSP": "RenewableDispatch",
    "RTPV": "RenewableNonDispatch",
    "HYDRO": "HydroDispatch",
    "SYNC_COND": "SynchronousCondenser",
    "STORAGE": "EnergyReservoirStorage",
}
```

Common fields: `name=GEN UID`, `bus` via `idx.bus_id_by_number[Bus ID]`, `active_power=MW Inj`, `reactive_power=MVAR Inj`, `active_power_limits={"min":PMin MW,"max":PMax MW}`, `reactive_power_limits={"min":QMin MVAR,"max":QMax MVAR}`, `rating=hypot(PMax, QMax)`, `base_power=Base MVA`. Thermal extras: `ramp_limits={"up":Ramp Rate MW/Min,"down":same}`, `time_limits={"up":Min Up Time Hr,"down":Min Down Time Hr}`, `fuel` mapped to the `ThermalFuels`-equivalent enum in the models (`Oil`→`DISTILLATE_FUEL_OIL`, `Coal`→`COAL`, `NG`→`NATURAL_GAS`, `Nuclear`→`NUCLEAR` — enumerate the enum members from `core/models.py` and error on unmapped fuel), `prime_mover_type=Unit Type` (CC/CT/ST/… — map STEAM→ST, NUCLEAR→ST). Storage joins `storage.csv` on `GEN UID` for volumes/efficiency.

Cost (thermal only, verified against `101_CT_1` in the reference rts.json — `start_up=51.747`, `fuel_cost=0.0103494`, PIECEWISE_STEP x `[8,12,16,20]`, y `[9456,9476,10352]`, `initial_input=104912.0`):
- `x_coords[k] = Output_pct_k × PMax MW` for the nonempty blocks
- `y_coords[k] = HR_incr_k` for k ≥ 1
- `initial_input = HR_avg_0 × x_coords[0]` (BTU/kWh × MW → MBTU/h consistency: confirm the ×1000 factor by reproducing 104912.0 = 13114 × 8 exactly)
- `fuel_cost = Fuel Price $/MMBTU / 1000`
- `start_up = Non Fuel Start Cost $ + Start Heat Cold MBTU × Fuel Price $/MMBTU`; `shut_down = Non Fuel Shutdown Cost $`
- `vom_cost` = INPUT_OUTPUT linear curve with `proportional_term = VOM`
- Renewables/hydro: the models' zero/renewable cost variant (check `RenewableGenerationCost` in models.py).

- [ ] **Step 1: failing tests** — counts per `UNIT_TYPE_TO_MODEL` group-by of gen.csv; exact cost-block assertions for `101_CT_1` as literal expected values from the formulas above.
- [ ] **Step 2–4:** FAIL → implement → PASS; `doc.validate()` in test. Checkpoint.

---

### Task 6: Loads, storage join, reserves (`demand.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/demand.py`, `python/tests/test_demand.py`

**Interfaces:**
- Consumes: `TopologyIndex`, generator ids from Task 5.
- Produces: `add_loads(doc, source, idx) -> None` (one `PowerLoad` per bus with `MW Load != 0`: `active_power=max_active_power=MW Load`, `reactive_power=max_reactive_power=MVAR Load`, `base_power=100.0`); `add_reserves(doc, source, idx, gen_ids) -> dict[str, int]` (reserve id by product name): `VariableReserve` with `time_frame=Timeframe (sec)`, `requirement=Requirement (MW)`, `reserve_direction` from `Direction`, `sustained_time=3600.0`, fractions 1.0/0.0 as in the reference; then one service-association row per eligible generator (region membership via the generator's bus→area, category via `UNIT_TYPE_TO_MODEL`).

- [ ] **Steps:** failing test (load count == nonzero-load buses; reserve count == reserves.csv rows; association rows > 0 and all ids resolve) → implement → PASS → `doc.validate()`. Checkpoint.

---

### Task 7: Parquet sidecar writer (`sidecar.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/sidecar.py`, `python/tests/test_sidecar.py`

**Interfaces:**
- Produces: `SidecarWriter(case_dir: Path)` with `write(timestamps: pd.DatetimeIndex, values: np.ndarray) -> tuple[str, str]` returning `(uri, data_hash)`; content-dedup by hash; `data_hash(values) -> str`.

```python
def data_hash(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values, dtype="<f8").tobytes()).hexdigest()
```

`write` builds `pyarrow.table({"timestamp": timestamps_utc_ms, "value": values_f8})` and writes `timeseries/ts_<hash[:16]>.parquet` only if absent; timestamps stored as `pa.timestamp("ms", tz="UTC")`.

- [ ] **Steps:** failing test (same array twice → one file, same uri; hash is 64 hex; parquet reads back equal values and UTC ms timestamps) → implement → PASS. Checkpoint.

---

### Task 8: Time series attachment (`timeseries.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/timeseries.py`, `python/tests/test_timeseries.py`

**Interfaces:**
- Consumes: `SidecarWriter`, `SystemDocument`, `TopologyIndex`, generator/reserve id maps.
- Produces: `attach_time_series(doc, source, sidecar, owners) -> None` where `owners` bundles the id maps; internal `read_profile(csv_path, column, resolution) -> (pd.DatetimeIndex, np.ndarray)` parsing RTS `Year,Month,Day,Period` layouts (DAY_AHEAD hourly, Period 1–24 → PT1H; REAL_TIME 5-minute, Period 1–288 → PT5M; timestamps UTC).

Pointer resolution (`timeseries_pointers.csv`: `Simulation,Category,Object,Parameter,Scaling Factor,Data File`):
- owner: `Category == "Generator"` → generator id by `Object`; `Category in ("Area","Region","Zone")` → `Area` by name; `Category == "Reserve"` → reserve id. Unmapped category → `ValueError` naming the row.
- `name`/`component_field` from `Parameter` (`"PMax MW"` → `"max_active_power"`, `"Requirement (MW)"`/reserve rows → `"requirement"`, load rows → `"max_active_power"`; unmapped → error).
- values × `Scaling Factor`, natural MW.
- association: `SingleTimeSeries` model from `power_openapi_models.timeseries.models` with `association_id=doc.next_id()`, `owner_id/owner_type/owner_category="Component"`, `time_series_type="SingleTimeSeries"`, `features={}`, `uri`, `data_hash`, `element_type` = the scalar float member of the `ElementType` enum (read it from `timeseries/models.py`), `element_shape=[]`, `units="MW"`, `quantity_kind="active_power"`, `unit_system="NATURAL_UNITS"`, `component_field`, `initial_timestamp`, `resolution` (`"PT3600S"`/`"PT300S"` — match the `Period` pattern the schema expects; check the field's validator), `length`.
- Set `doc.time_series_storage_file = "timeseries"`.

- [ ] **Steps:** failing tests (a DAY_AHEAD wind pointer yields length 8784×? — assert length equals rows in its data file; every association's `uri` exists on disk; resolutions only PT3600S/PT300S; all owner ids resolve) → implement → PASS. Checkpoint.

---

### Task 9: Driver, validation, and case build (`build_rts.py`)

**Files:**
- Create: `python/src/rts_gmlc_case/build.py`, `python/build_rts.py`, `python/tests/test_build.py`

**Interfaces:**
- Produces: `build_case(case_dir: Path) -> SystemDocument` running Tasks 3–8 in order and writing `case_dir/system.json` + sidecar; `read_case(case_dir) -> SystemDocument` re-parsing every component bucket through its pydantic class (type name → class via a registry dict built from the domain modules' `__all__`) and re-running `validate()`.

- [ ] **Steps:** failing test — `build_case(tmp)` then `read_case(tmp)`: bucket-by-bucket `model_dump()` equality; every parquet file referenced exactly once or more and no orphan files; rebuild is byte-identical (`system.json` compared as bytes — determinism). Implement → PASS. Then run `uv run python build_rts.py ../cases/rts-python` (the dir the cross-language test in the Julia plan Task 10 expects) and report component counts. Checkpoint.

---

### Task 10: Tutorial chapters

**Files:**
- Create: `python/docs/01-setup.md` … `python/docs/08-validation.md`, expand `python/README.md`

Chapter per stage, each: what the data looks like (head of the CSV), which models are used and where to find them (`python3 -c "from power_openapi_models.operations import models; ..."` enumeration snippet), the mapping table, the runnable command, and what to check. Chapter 02 explains the document JSON shape and why ids are integers; chapter 07 states the full sidecar contract verbatim from the design doc. Sienna appears nowhere except the package-name install line.

- [ ] **Steps:** write chapters; verify every code snippet by executing it (`uv run python -c ...` or copying into a scratch file — no unexecuted snippets); README links chapters in order. Checkpoint: full `uv run pytest` green, report count.
