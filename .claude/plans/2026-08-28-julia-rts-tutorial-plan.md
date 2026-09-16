# Julia RTS OpenAPI Case Tutorial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Julia package + markdown tutorial that builds RTS-GMLC into an OpenAPI case document (`system.json` + parquet `timeseries/` sidecar) using only the `PowerOpenAPIModels` packages, CSV/DataFrames, and Parquet2.

**Architecture:** Package `RTSGMLCCase` mirroring the Python project module-for-module (`topology.jl`, `branches.jl`, `generation.jl`, `demand.jl`, `sidecar.jl`, `timeseries.jl`, `build.jl`). Unlike Python, the document container is NOT hand-written: `PowerOpenAPIModels.SystemDocument` already provides ids, association tables, `validate_document`, `write_document`, `read_document`. Component structs come from the domain packages (`PowerOperationsOpenAPIModels`, `PowerCoreOpenAPIModels`, `PowerTimeSeriesOpenAPIModels`).

**Tech Stack:** Julia ≥1.10; deps `PowerOpenAPIModels` + domain packages via `[sources]` path pins to `../../PowerOpenAPIModels/*` (unregistered), `CSV`, `DataFrames`, `Parquet2`, `SHA`, `JSON3`, `TimeZones`, `Dates`, `Downloads`, `Tar`, `CodecZlib`; `Test` in `test/Project.toml`.

**Spec:** `.claude/plans/2026-08-28-openapi-rts-tutorials-design.md`

## Global Constraints

- No Sienna reference except the `PowerOpenAPIModels`/`Power*OpenAPIModels` package names: no IS/PSY/PTDP deps, no HDF5, no Sienna URLs in tutorial prose.
- Natural units: `SystemDocument(100.0; unit_system = "NATURAL_UNITS")`; branch r/x/b per-unit on `base_power = 100.0`; angles radians.
- Sidecar contract exactly as the design doc: `timeseries/ts_<hash16>.parquet` with `timestamp` (ms, UTC) + `value` (float64) columns; `data_hash` = SHA-256 of float64-LE bytes; `uri = "timeseries/ts_<hash16>.parquet"`; `time_series_storage_file = "timeseries"`.
- Deterministic build, same stage order as Python: topology → branches → generation → loads/storage → reserves → time series. The cross-language test (Task 10) depends on identical id sequences — where the Python plan sorts (e.g. area names), sort identically here.
- Julia style: user-preferences rules apply — no ternaries, no `isa` gates, `function ... end` with explicit `return`, `iszero(x)`, no `Union{Nothing,T}` sentinels; error loudly on unmapped data with type/name context.
- After each task: compile check `julia --project=julia/RTSGMLCCase -e 'using RTSGMLCCase'`, then run tests with `julia --project=julia/RTSGMLCCase/test test/runtests.jl` (test deps in `test/Project.toml`). Format with JuliaFormatter before finishing.
- **Git policy:** leave changes unstaged (`git add -N` for new files). Never commit or push; "Checkpoint" = stop and report.

---

### Task 1: Package scaffold + pinned data download

**Files:**
- Create: `julia/RTSGMLCCase/Project.toml`, `julia/RTSGMLCCase/src/RTSGMLCCase.jl`, `julia/RTSGMLCCase/src/data.jl`, `julia/RTSGMLCCase/test/Project.toml`, `julia/RTSGMLCCase/test/runtests.jl`, `julia/RTSGMLCCase/test/test_data.jl`

**Interfaces:**
- Produces: `rts_source_dir() -> String` — downloads/caches RTS-GMLC v0.2.2 into `<repo-root>/data/RTS-GMLC/` (same location the Python project uses; whichever runs first populates it), verifies sha256, returns the `RTS_Data` path. Constant `SOURCE_URL`, `SOURCE_SHA256`.

- [ ] **Step 1: scaffold** — `Project.toml` with a UUID (`julia -e 'using UUIDs; println(uuid4())'`), deps listed above, and:

```toml
[sources]
PowerOpenAPIModels = {path = "../../../PowerOpenAPIModels/PowerOpenAPIModels.jl"}
PowerCoreOpenAPIModels = {path = "../../../PowerOpenAPIModels/PowerCoreOpenAPIModels.jl"}
PowerOperationsOpenAPIModels = {path = "../../../PowerOpenAPIModels/PowerOperationsOpenAPIModels.jl"}
PowerTimeSeriesOpenAPIModels = {path = "../../../PowerOpenAPIModels/PowerTimeSeriesOpenAPIModels.jl"}
```

(Verify each subpackage's actual name/UUID from its own Project.toml; add `OpenAPI` if the model constructors require it directly.) `test/Project.toml` gets `Test`, `CSV`, `DataFrames`, `Parquet2`, `JSON3` plus the same `[sources]`.

- [ ] **Step 2: failing test**

```julia
# test/test_data.jl
@testset "source data" begin
    src = RTSGMLCCase.rts_source_dir()
    for name in ("bus.csv", "branch.csv", "gen.csv", "reserves.csv", "timeseries_pointers.csv")
        @test isfile(joinpath(src, "SourceData", name))
    end
end
```

- [ ] **Step 3: implement `data.jl`**

```julia
const SOURCE_URL = "https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz"
const SOURCE_SHA256 = "f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2"
const REPO_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))

function rts_source_dir()
    root = joinpath(REPO_ROOT, "data", "RTS-GMLC")
    marker = joinpath(root, "RTS_Data", "SourceData", "bus.csv")
    if !isfile(marker)
        mkpath(root)
        tarball = Downloads.download(SOURCE_URL)
        digest = bytes2hex(open(SHA.sha256, tarball))
        if digest != SOURCE_SHA256
            error("checksum mismatch for $SOURCE_URL: $digest")
        end
        open(tarball) do io
            stream = CodecZlib.GzipDecompressorStream(io)
            extracted = Tar.extract(stream)
            inner = only(readdir(extracted; join = true))
            for child in readdir(inner; join = true)
                mv(child, joinpath(root, basename(child)); force = true)
            end
        end
    end
    return joinpath(root, "RTS_Data")
end
```

- [ ] **Step 4: run** — instantiate then `julia --project=test test/runtests.jl` from the package dir → PASS.
- [ ] **Step 5: Checkpoint** — report; leave unstaged.

---

### Task 2: Document conventions module (`document.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/document.jl`, `julia/RTSGMLCCase/test/test_document.jl`

**Interfaces:**
- Produces: `new_document() -> PowerOpenAPIModels.SystemDocument` (base 100.0, NATURAL_UNITS); re-exports/aliases `const PD = PowerOpenAPIModels`; helper `add!(doc, model) -> Int` that assigns `next_id!` when unset, calls `PD.add_component!`, and returns the id.

This task is thin on purpose — the umbrella package already owns the container. Its test doubles as the tutorial's chapter-02 demonstration.

- [ ] **Step 1: failing test**

```julia
@testset "document basics" begin
    doc = RTSGMLCCase.new_document()
    area = PowerOperationsOpenAPIModels.Area(;
        id = PowerOpenAPIModels.next_id!(doc), name = "1",
        peak_active_power = 0.0, peak_reactive_power = 0.0)
    PowerOpenAPIModels.add_component!(doc, area)
    PowerOpenAPIModels.validate_document(doc)
    @test length(PowerOpenAPIModels.get_components(doc, "Area")) == 1
end
```

(Adjust the `Area` keyword set to `model_Area.jl`'s actual fields before running; every generated model is a keyword-constructed `OpenAPI.APIModel`.)

- [ ] **Steps 2–4:** FAIL → implement → PASS. Checkpoint.

---

### Task 3: Topology (`topology.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/topology.jl`, `julia/RTSGMLCCase/test/test_topology.jl`

**Interfaces:**
- Produces: `add_topology!(doc, source::AbstractString) -> TopologyIndex` with `struct TopologyIndex; bus_id_by_number::Dict{Int, Int}; area_id_by_name::Dict{String, Int}; zone_id_by_name::Dict{String, Int}; end`.

Mapping identical to the Python plan Task 3: `Area` per distinct `Area` column value and `LoadZone` per distinct `Zone` (stringified, added in sorted order); `ACBus` per row with `number`, `name`, `base_voltage = BaseKV`, `bustype` normalized to the `ACBusType` enum (check `model_ACBusType.jl`; RTS spells `Ref`), `angle = deg2rad(V Angle)`, `magnitude = V Mag`, `voltage_limits` min 0.95 / max 1.05, `area`/`load_zone` ids, `available = true`. Nonzero `MW Shunt G`/`MVAR Shunt B` → `error("unexpected shunt at bus $number")`.

- [ ] **Step 1: failing test** — counts vs `CSV.read(bus.csv)` group-bys; bus 101 named "Abel" with `angle ≈ deg2rad(row."V Angle")`.
- [ ] **Steps 2–4:** FAIL → implement (`CSV.read(path, DataFrame)`, iterate `eachrow` in file order) → PASS → `validate_document`. Checkpoint.

---

### Task 4: Branches (`branches.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/branches.jl`, `julia/RTSGMLCCase/test/test_branches.jl`

**Interfaces:**
- Consumes: `TopologyIndex`.
- Produces: `add_branches!(doc, source, idx)`; internal `arc_id!(doc, cache::Dict{Tuple{Int, Int}, Int}, from_id, to_id) -> Int`.

Mapping identical to Python Task 4: `iszero(row."Tr Ratio")` → `Line` (r, x, `b = (from = B/2, to = B/2)`, `g` zeros, `base_power = 100.0`, ratings Cont/LTE/STE, `angle_limits` ±3.1416, flows 0.0, `name = UID`); otherwise `TransformerCircuit` + `TwoWindingTransformer` (fields per `model_TransformerCircuit.jl` / `model_TwoWindingTransformer.jl`, values per the reference rts.json: `tap = Tr Ratio`, `alpha = 0.0`, `control_objective = "FIXED"`, `control_limits` 0.9/1.1, `shunt_location = "PRIMARY"`, zero `magnetizing_shunt`). `dc_branch.csv` → `TwoTerminalGenericHVDCLine` over a fresh arc.

- [ ] **Step 1: failing test** — same partition/dedup assertions as the Python plan (line count = rows − transformer rows; unique arc pairs; `validate_document` passes); dev-only spot check when `/Users/jdlara/cache/psy6/PowerTableDataParser.jl/data/rts.json` exists: line "A1" `r = 0.003`, `x = 0.014`, `rating = 175.0`.
- [ ] **Steps 2–4:** FAIL → implement → PASS. Checkpoint.

---

### Task 5: Generators and costs (`generation.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/generation.jl`, `julia/RTSGMLCCase/test/test_generation.jl`

**Interfaces:**
- Consumes: `TopologyIndex`.
- Produces: `add_generation!(doc, source, idx) -> Dict{String, Int}` (id by `GEN UID`); `thermal_cost(row) -> PowerCoreOpenAPIModels.ThermalGenerationCost`; `const UNIT_TYPE_TO_MODEL` — the same 11-entry table as the Python plan Task 5 (NUCLEAR/STEAM/CT/CC → `"ThermalStandard"`, WIND/PV/CSP → `"RenewableDispatch"`, RTPV → `"RenewableNonDispatch"`, HYDRO → `"HydroDispatch"`, SYNC_COND → `"SynchronousCondenser"`, STORAGE → `"EnergyReservoirStorage"`). Unmapped unit type or fuel → `error` naming the row.

Field and cost formulas are identical to the Python plan Task 5, including the `101_CT_1` ground truth (`start_up = 51.747`, `fuel_cost = 0.0103494`, PIECEWISE_STEP x `[8.0, 12.0, 16.0, 20.0]`, y `[9456.0, 9476.0, 10352.0]`, `initial_input = 104912.0`). Dispatch construction by target model name through a small `Dict{String, Function}` of builder functions — one typed builder per component type, no `isa` branching. Storage rows join `storage.csv` on `GEN UID`.

- [ ] **Step 1: failing tests** — counts per unit-type group-by; exact `101_CT_1` cost assertions computed from the formulas as literals.
- [ ] **Steps 2–4:** FAIL → implement → PASS → `validate_document`. Checkpoint.

---

### Task 6: Loads and reserves (`demand.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/demand.jl`, `julia/RTSGMLCCase/test/test_demand.jl`

**Interfaces:**
- Consumes: `TopologyIndex`, generator id map.
- Produces: `add_loads!(doc, source, idx)` — one `PowerLoad` per bus with nonzero `MW Load` (`active_power = max_active_power = MW Load`, reactive likewise, `base_power = 100.0`, `name` = bus name); `add_reserves!(doc, source, idx, gen_ids) -> Dict{String, Int}` — `VariableReserve` (`time_frame`, `requirement`, `reserve_direction`, `sustained_time = 3600.0`, `max_output_fraction = 1.0`, `max_participation_factor = 1.0`, `deployed_fraction = 0.0`) plus `PowerOpenAPIModels.add_service_association!` rows for eligible generators (bus→area region membership × eligible categories, mirroring the Python rules).

- [ ] **Steps:** failing test (load count == count of nonzero `MW Load` rows == 51; reserve count == 7; associations resolve under `validate_document`) → implement → PASS. Checkpoint.

---

### Task 7: Parquet sidecar writer (`sidecar.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/sidecar.jl`, `julia/RTSGMLCCase/test/test_sidecar.jl`

**Interfaces:**
- Produces: `struct SidecarWriter; dir::String; written::Set{String}; end`, `SidecarWriter(case_dir)` (creates `timeseries/`), `write_series!(w, timestamps::Vector{ZonedDateTime}, values::Vector{Float64}) -> Tuple{String, String}` returning `(uri, data_hash)`, `data_hash(values) -> String`.

```julia
function data_hash(values::Vector{Float64})
    bytes = reinterpret(UInt8, htol.(values))
    return bytes2hex(SHA.sha256(collect(bytes)))
end
```

`write_series!` writes via `Parquet2.writefile(path, (timestamp = ..., value = values))` with millisecond-UTC timestamps and skips files already in `written`/on disk. **Cross-language pin:** the parquet `timestamp` column must read back in Python as `timestamp[ms, tz=UTC]` — check Parquet2's timestamp keyword options and set them explicitly.

- [ ] **Steps:** failing test (dedup; 64-hex hash; Parquet2 read-back equals input; hash of `[1.0, 2.0, 3.0]` equals the literal Python produces — compute it once with `python3` and inline it) → implement → PASS. Checkpoint.

---

### Task 8: Time series attachment (`timeseries.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/timeseries.jl`, `julia/RTSGMLCCase/test/test_timeseries.jl`

**Interfaces:**
- Consumes: `SidecarWriter`, id maps from Tasks 3/5/6.
- Produces: `attach_time_series!(doc, source, sidecar, owners)` with `struct Owners; idx::TopologyIndex; gen_ids::Dict{String, Int}; reserve_ids::Dict{String, Int}; end`; internal `read_profile(csv_path, column, resolution)` parsing the RTS `Year, Month, Day, Period` layouts (DAY_AHEAD Period 1–24 → `"PT3600S"`; REAL_TIME Period 1–288 → `"PT300S"`; UTC timestamps).

Pointer resolution and association fields identical to the Python plan Task 8: owner by `Category` (Generator → gen id, Area/Region/Zone → Area, Reserve → reserve id; unmapped → `error` naming the row), `name`/`component_field` from `Parameter` via an explicit map, values × `Scaling Factor` in natural MW, and a `PowerTimeSeriesOpenAPIModels.SingleTimeSeries` per row: `association_id = next_id!(doc)`, `owner_category = "Component"`, `features = Dict{String, Any}()`, `uri`, `data_hash`, `element_type` = the scalar float member of the generated element-type enum, `element_shape = Int[]`, `units = "MW"`, `quantity_kind = "active_power"`, `unit_system = "NATURAL_UNITS"`, `initial_timestamp`, `resolution`, `length`. Attach with `PowerOpenAPIModels.add_time_series_association!`; set the document's `time_series_storage_file` to `"timeseries"` (via its field/setter — see `document.jl:98`).

- [ ] **Steps:** failing tests (association length equals its data-file row count; every `uri` exists; only the two resolutions; owners resolve under `validate_document`) → implement → PASS. Checkpoint.

---

### Task 9: Driver and round-trip (`build.jl`)

**Files:**
- Create: `julia/RTSGMLCCase/src/build.jl`, `julia/RTSGMLCCase/build_rts.jl`, `julia/RTSGMLCCase/test/test_build.jl`

**Interfaces:**
- Produces: `build_case(case_dir::AbstractString) -> SystemDocument` (stages in the fixed order; `validate_document`; `write_document(doc, joinpath(case_dir, "system.json"))` — match `write_document`'s actual signature at `document.jl:604`); `read_case(case_dir)` = `PowerOpenAPIModels.read_document` + `validate_document`.

- [ ] **Steps:** failing test — build into `mktempdir()`, read back, compare component counts per bucket and `document_tree` equality between written and re-read documents; rebuild determinism (`read(system.json)` bytes equal across two builds). Implement → PASS. Run `julia --project=. build_rts.jl ../../cases/rts-julia` (the dir Task 10's cross-language test expects), report counts. Checkpoint.

---

### Task 10: Cross-language equivalence test

**Files:**
- Create: `julia/RTSGMLCCase/test/test_cross_language.jl`, `python/tests/test_cross_language.py` (same assertion, either side may run it)

**Interfaces:**
- Consumes: both built cases: `cases/rts-julia/` and `cases/rts-python/` (each project's driver takes the output dir as an argument).

- [ ] **Step 1: failing test (Julia side)**

```julia
@testset "cross-language equivalence" begin
    jl = JSON3.read(read(joinpath(CASES, "rts-julia", "system.json")))
    py = JSON3.read(read(joinpath(CASES, "rts-python", "system.json")))
    @test keys(jl) == keys(py)
    for type_name in keys(jl["components"])
        @test length(jl["components"][type_name]) == length(py["components"][type_name])
    end
    jl_hashes = Set(a["data_hash"] for a in jl["time_series_associations"])
    py_hashes = Set(a["data_hash"] for a in py["time_series_associations"])
    @test jl_hashes == py_hashes
end
```

Skip (with a printed instruction) when either case folder is missing rather than failing.

- [ ] **Step 2:** build both cases, run the test. Every mismatch is a real finding: fix the divergent side (the design doc's conventions arbitrate; where silent, the Julia `SystemDocument` tree wins). Iterate to PASS. Stretch (only if time permits): full canonicalized-JSON equality, not just counts — sort each bucket by `id` and compare trees, excluding fields the two sides legitimately mint differently (none expected).
- [ ] **Step 3: Checkpoint** — full suites in both projects, report pass counts.

---

### Task 11: Tutorial chapters + formatter

**Files:**
- Create: `julia/RTSGMLCCase/docs/01-setup.md` … `08-validation.md`, `julia/RTSGMLCCase/README.md`

Mirror the Python chapters section-for-section; language-specific content limited to environment setup (`[sources]` path pins vs registry install note), keyword-constructor idiom, and `read_document`/`validate_document` usage. Chapter 07 restates the sidecar contract verbatim. Execute every snippet before it lands in prose.

- [ ] **Steps:** write chapters; run every snippet; run JuliaFormatter over `src/` and `test/`; final full test run in both projects; report counts. Checkpoint.
