# Generic Grid-Data Cases with the OpenAPI Model Packages — Design

**Date:** 2026-08-28
**Status:** Draft for review
**Implements to:** three plans in this folder — `2026-08-28-python-rts-tutorial-plan.md`,
`2026-08-28-julia-rts-tutorial-plan.md`, `2026-08-28-grid-data-skill-plan.md`

## Goal

Two mirrored tutorial projects — one Python, one Julia — that build the complete RTS-GMLC system
as a portable OpenAPI case document (JSON + parquet time series sidecar), using only:

- **Python:** `power-openapi-models` (pydantic v2 models) + pandas/pyarrow
- **Julia:** `PowerOpenAPIModels` umbrella + domain packages + CSV/DataFrames/Parquet2

The audience is engineers who want a validated, language-neutral grid data interchange format and
have **no interest in Sienna's modeling machinery**. Except for the two package names, no code,
prose, or dependency references Sienna, InfrastructureSystems, PowerSystems, or
PowerTableDataParser. No HDF5, no InfraStore — time series ride in a folder of parquet files.

Effectively this re-writes PowerTableDataParser's RTS ingest twice, generically. PTDP's
`src/openapi/` layer and its emitted `data/rts.json` are our private reference for conventions and
spot-checks; they are never cited in tutorial output.

A third deliverable is a Claude Code skill that packages the whole workflow (model packages,
document shape, sidecar convention, validation) so future sessions and adopters get it right
without re-deriving it.

## Repository layout (this repo, `SchemasTutorials`)

```
SchemasTutorials/
├── python/                     # standalone uv project, package rts_gmlc_case
│   ├── pyproject.toml
│   ├── src/rts_gmlc_case/
│   ├── tests/
│   └── docs/                   # tutorial chapters 01…08 (markdown)
├── julia/RTSGMLCCase/          # standalone Julia package
│   ├── Project.toml            # [sources] path pins to ../../PowerOpenAPIModels/*
│   ├── src/
│   ├── test/
│   └── docs/                   # tutorial chapters 01…08 (markdown)
├── cases/rts/                  # build output (gitignored): system.json + timeseries/
└── .claude/
    ├── plans/                  # these documents
    └── skills/grid-openapi-cases/   # the skill (deliverable 3)
```

The two projects **mirror each other stage for stage** (same module split, same function names
modulo language casing) so a reader can diff them and so validation is mechanical.

## Data source

RTS-GMLC v0.2.2 GitHub tarball, pinned:

- URL `https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz`
- sha256 `f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2`

Each project ships a `download_data` step (stdlib download + checksum + untar into a shared
`data/RTS-GMLC/` at repo root). Input tables: `RTS_Data/SourceData/{bus,branch,gen,dc_branch,
reserves,storage,timeseries_pointers}.csv` and `RTS_Data/timeseries_data_files/**`. We read RTS's
own CSVs directly — **not** the Sienna descriptor/pointer fixtures PTDP uses.

## The case document

The Julia umbrella package already owns the document: `PowerOpenAPIModels.SystemDocument` with
`add_component!`, `next_id!`, `add_time_series_association!`, `add_service_association!`,
`add_supplemental_attribute!`, `validate_document`, `write_document`, `read_document`
(`PowerOpenAPIModels.jl/src/document.jl`). The Julia tutorial uses it as-is.

The Python package has models only — no document container. The Python tutorial therefore includes
a small hand-written `document.py` (~150 lines): a `SystemDocument` pydantic model holding
`base_power`, `unit_system`, `components: dict[type_name, list]`, the association tables, `ext`,
and `time_series_storage_file`, with `add_component`, id allocation, validation (unique ids,
resolved integer references), and JSON write/read. **Its serialized tree must match
`PowerOpenAPIModels.document_tree` key-for-key** (read `document.jl:563` before writing it); the
cross-language test enforces this. This is also a teaching point: the document is just JSON.

Known drift to absorb during implementation, not paper over: PTDP's checked-in `data/rts.json`
predates the current TimeSeriesAssociation schema (it has `time_series_uuid` /
`scaling_factor_multiplier`; current schema has `association_id` / `uri` / `element_type` / …).
The **generated model packages are authoritative** for field shapes; `rts.json` is a reference
only for component values and counts.

## Parquet time series sidecar — the shared contract

This is the piece both tutorials and the skill must state identically:

- Sidecar is a folder named `timeseries/` next to `system.json`; the document's
  `time_series_storage_file` field holds the folder name `"timeseries"` (the schema leaves the
  locator format to the store — we are the store).
- One parquet file per distinct series: `ts_<first 16 hex of data_hash>.parquet`, two columns:
  `timestamp` (timestamp[ms], UTC) and `value` (float64).
- `data_hash` = SHA-256 hex over the value vector's float64 little-endian bytes. Deterministic
  across both languages; it is the dedup key (two owners sharing a profile point at one file) and
  the cross-language equivalence check for the dense data.
- Association `uri` = `"timeseries/ts_<hash16>.parquet"` (relative to the document).
- `association_id`: minted sequentially from the document's own id counter at attach time.

## Component mapping (both languages, identical)

Natural units throughout: document `unit_system = "NATURAL_UNITS"`, MW/MVAR/MVA/kV as in the
source. Conventions pinned from PTDP's emitter where RTS is ambiguous:

| Source | Emits | Notes |
|---|---|---|
| `bus.csv` | `Area`, `LoadZone`, `ACBus`, `PowerLoad` | angle degrees→radians; `voltage_limits` 0.95/1.05 (RTS has none); one `PowerLoad` per bus with nonzero `MW Load` (51 of 73); nonzero shunt columns are an error (RTS has none) |
| `branch.csv` | `Arc` (unique from,to), `Line` (Tr Ratio == 0), `TransformerCircuit` + `TwoWindingTransformer` (Tr Ratio ≠ 0) | r/x/b stay per-unit on `base_power = 100.0` (matches rts.json); ratings natural MVA from Cont/LTE/STE; angle_limits ±π |
| `gen.csv` | by `Unit Type`: NUCLEAR/STEAM/CT/CC → `ThermalStandard`; WIND/PV/CSP → `RenewableDispatch`; RTPV → `RenewableNonDispatch`; HYDRO → `HydroDispatch`; SYNC_COND → `SynchronousCondenser`; STORAGE → `EnergyReservoirStorage` (join `storage.csv`) | deliberate simplification vs PTDP: plain `HydroDispatch`, no HydroTurbine/HydroReservoir pair — stated in the tutorial |
| `gen.csv` heat-rate blocks | `ThermalGenerationCost` with PIECEWISE_STEP incremental fuel curve | x = `Output_pct_k × PMax`, y = `HR_incr_k` (BTU/kWh); `fuel_cost = Fuel Price $/MMBTU / 1000`; `start_up = Non Fuel Start Cost + Start Heat Cold × Fuel Price`; verify each formula against a named rts.json generator (e.g. `101_CT_1`: start_up 51.747, fuel_cost 0.0103494) |
| `dc_branch.csv` | `TwoTerminalGenericHVDCLine` | 1 row |
| `reserves.csv` | `VariableReserve` + service associations | contributors resolved from Eligible Regions × Eligible Device Categories/SubCategories |
| `timeseries_pointers.csv` | `SingleTimeSeries` associations + parquet files | both DAY_AHEAD (PT1H) and REAL_TIME (PT5M); owners: region rows → `Area`, generator rows → the generator, reserve rows → the `VariableReserve`; values in natural MW, `unit_system = "NATURAL_UNITS"` |
| `gen.csv`/`branch.csv` FOR/MTTR/MTTF | *(stretch)* outage supplemental attributes + association rows | demonstrates the supplemental-attribute table; skippable without breaking anything |

## Verification strategy

1. **Per-stage unit tests** (pytest / Test) on small literal fixtures — no network.
2. **Source-derived counts**: component counts asserted against group-bys of the CSVs themselves
   (not hardcoded, not Sienna-derived).
3. **Round-trip**: Julia `read_document` + `validate_document` on the written case; Python
   re-parse through pydantic models + own validator.
4. **Cross-language equivalence (flagship)**: canonicalized `system.json` from both builds are
   equal, and the sets of parquet `data_hash`es are equal. Requires both builds to be
   deterministic: iterate CSV rows in file order, mint ids in a fixed stage order.
5. **Reference spot-checks** (dev-only test, not tutorial content): selected values against PTDP's
   `data/rts.json` (bus 101 angle, line A1 impedances, `101_CT_1` cost block).

## Tutorial format

Markdown chapters under each project's `docs/`, one per build stage, each ending with a runnable
command; `build_rts.py` / `build_rts.jl` scripts run the whole pipeline. Chapters:
01 setup & data, 02 the document, 03 topology, 04 branches, 05 generators & costs,
06 loads/storage/reserves, 07 time series & parquet sidecar, 08 validation & reading the case back.

## The Claude skill (deliverable 3)

`SchemasTutorials/.claude/skills/grid-openapi-cases/` — triggers when a user wants to create,
read, validate, or convert grid case data with these packages. Carries the sidecar contract, the
document JSON shape, a model-package cheatsheet (where types live, how to enumerate them), the
validation commands, and pitfalls (id references, natural units, schema-vs-rts.json drift).
Written and tested per `superpowers:writing-skills`. Detail in its own plan.

## Alternatives considered

- **One parquet file per source CSV (wide tables)** — fewer files, but `uri` then needs a column
  fragment convention and dedup is lost. Rejected: per-series files keep `uri` trivially resolvable.
- **Hydro as HydroTurbine + HydroReservoir (PTDP-faithful)** — doubles hydro complexity for no
  tutorial value. Rejected; noted as an extension exercise in chapter 05.
- **Upstreaming a document container into `power-openapi-models`** — right long-term home, out of
  scope here; the tutorial's `document.py` is the prototype. Flagged in the skill as future work.
- **Notebooks for Python** — rejected for symmetry with Julia and diff-ability; plain markdown +
  scripts.

## Open questions for the user

1. Project/folder names (`python/` + `julia/RTSGMLCCase/`) acceptable?
2. Should the stretch outage-supplemental-attribute stage be in scope for v1?
3. Should the skill live in this repo (travels with tutorials) or in `~/.claude/skills/`?
