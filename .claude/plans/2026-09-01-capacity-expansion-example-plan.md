# RTS Capacity-Expansion Example — Implementation Plan

**Date:** 2026-09-01
**Status:** Ready to execute
**Spec:** user request + rulings R35–R39 in the campaign facts file
**Facts and field mapping:**
- `<scratchpad>/CAMPAIGN-FACTS.md` (rulings R35–R39, plus R1–R34 which still bind)
- `<scratchpad>/preflight-investments.md` (field-by-field source mapping)

## Goal

Extend the RTS tutorials with a **capacity-expansion example** that populates the investments
half of the OpenAPI schema from the ReEDS-style `RTS_inputs` dataset, in **Python and Julia**,
producing **one combined document** whose operations and investment components share a single
id space.

## Architecture

No new container (R36). `SystemDocument.components` is `dict[str, list[dict]]` keyed by type
name, so investment components bucket into the same document the operations stages already
fill. The combined builder runs the existing operations stages, then the investment stages,
against one `CaseDocument` and one id counter.

Output: `cases/rts-expansion/` — `system.json` + `timeseries/`. The existing
`cases/rts-python/` (operations only) stays as it is; this is an additional case, not a
replacement, so the operations tutorial's story is unaffected.

## Global constraints

- **RULE ZERO:** `power-openapi-models` and `PowerOpenAPIModels` are read-only. A task that
  seems to need a package change reports BLOCKED. This has already bitten once — the package
  was regenerated mid-campaign and removed an enum member we used.
- **No commits, no `git add`, no `git push`.** Work stays unstaged.
- **Runtime budget:** never run the unfiltered pytest suite; `-m "not slow"` only. Never run a
  full build inside a review or docs task. A reviewer was killed for stalling on this.
- **Provenance labelling is non-negotiable (R37).** Every field not derived from the dataset
  carries a comment at its construction site naming its external source, and appears in a docs
  table of dataset-derived vs external values.
- Failing test first, then implement. Keep the suite warning-clean under `-W error::UserWarning`.
- Errors name the offending row. No silent skips.

## What the dataset does and does not support

Stated up front because it shapes every task (R37):

| Backed by `RTS_inputs` | Invented, from NREL ATB or illustrative |
|---|---|
| `Node` (73 buses) | all 6 policy types |
| `Zone` / `TopologyMapping` | `TechnologyFinancialData` (all 6 fields) |
| `ExistingDevices` | `PortfolioFinancialData` (all 4 fields) |
| both transport technologies | capital costs on Supply/StorageTechnology |
| `DemandRequirement` load shape | `StorageTechnology.duration_limits` |

`supply_curve_cost_per_mw` (~$10k/MW) is a site **interconnection** cost. It is not a capital
cost and must not be used as one.

---

## Python tasks

### E1 — Dataset module, nodes, zones, topology mapping

**Files:** `python/src/rts_gmlc_case/investments/__init__.py`, `data.py`, `topology.py`; tests.

- `investments_source_dir()` — pinned download of the 16-file subset into
  `<repo>/data/RTS-investments/`, checksum-verified, mirroring `data.py`'s atomic
  extract-then-move and its all-files-present cache check. Do **not** fetch `rts_psy5.sqlite`
  or `RTS_load_hourly.h5`.
- `add_investment_topology(doc, source, idx)` → 73 `Node`, 3 `Zone`, `TopologyMapping`.
- **R38:** zones are the **3 RTS areas**, not the dataset's 5 ReEDS balancing areas. Map nodes
  to zones through `bus.csv`'s `Area` column; the `ba` column in `hierarchy_rts.csv` is
  deliberately unused. Assert the 5-BA structure is *not* what was emitted.
- Reuse the operations `TopologyIndex` so `Node` ids can be related to `ACBus` ids.

**Verify:** 73 nodes, 3 zones, every node mapped exactly once; node↔bus correspondence holds.

### E2 — Existing devices and supply technologies

**Files:** `investments/technologies.py`, `investments/costs.py`; tests.

- `ExistingDevices` from `capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv`.
- `SupplyTechnology` candidates for the technology classes the supply curves cover
  (`upv`, `wind-ons`), plus thermal and hydro classes from the generator database.
- **R39:** `power_systems_type` takes the exact PSY type names this campaign emits —
  `ThermalStandard`, `RenewableDispatch`, `HydroDispatch`, `EnergyReservoirStorage`. Test that
  every value equals a type name actually present in the document.
- **`costs.py` holds the entire external-cost surface in one place:** a small NREL ATB table
  with a module docstring stating the source, vintage and scenario, and a per-entry comment.
  Keeping it in one module makes the invented-vs-sourced boundary auditable at a glance and
  easy to replace wholesale.
- `TechnologyFinancialData` from the same module — all six fields external (R37).

**Verify:** counts derived from the CSVs; every `SupplyTechnology` resolves to a real zone;
every cost field traceable to a `costs.py` entry.

### E3 — Storage and transport technologies

**Files:** `investments/storage.py`, `investments/transport.py`; tests.

- `StorageTechnology` — capacity from the dataset where present; `duration_limits` external,
  since both duration source files contain **zero data rows** (R37).
- `NodalACTransportTechnology` from `transmission/transmission_capacity_init_AC_rts_nodal.csv`
  and `transmission_distance_cost_500kVac_nodal.csv`; `NodalHVDCTransportTechnology` from the
  `nonAC` and `500kVdc` files.
- Transport endpoints reference `Node` ids minted in E1. `trans_crp = 40` from `scalars.csv` is
  the one genuinely-sourced financial value — use it and say so.

**Verify:** transport counts match the CSV row counts; every from/to node id resolves.

### E4 — Demand requirement and its time series

**Files:** `investments/demand.py`; tests.

- `DemandRequirement` per zone, with the hourly profile from
  `loaddata/RTS_DA_regional_load.csv` written through the **existing** `SidecarWriter` —
  same contract, same content dedup, same `data_hash`.
- `value_of_lost_load` is required and unsourced → external, labelled.
- Reuse the operations `SingleTimeSeries` association shape (R32), including `PT1H`.

**Verify:** one association per zone; `uri`s exist; `length` equals the parquet row count;
resolution is `PT1H`.

### E5 — Policy constraints

**Files:** `investments/policy.py`; tests.

Six types, **all illustrative** (R37): `CarbonCaps`, `CarbonTax`, `CapacityReserveMargin`,
`EnergyShareRequirements`, `MinimumCapacityRequirements`, `MaximumCapacityRequirements`.

- One module, one docstring stating plainly that no value here comes from `RTS_inputs` and that
  these are a worked scenario a reader is expected to replace.
- Values should be *plausible* for RTS scale rather than round placeholders — an 80%-by-2050
  carbon cap trajectory, a reserve margin in the usual 10–15% band — so the example demonstrates
  a realistic problem shape.

**Verify:** each type constructs and validates; every zone/technology reference resolves.

### E6 — Combined driver, round-trip, validation

**Files:** `investments/build.py`, `build_expansion.py` CLI, tests.

- `build_expansion_case(case_dir)` — operations stages in their existing fixed order, then
  investment stages, on **one** `CaseDocument` with **one** id counter. Validate, write.
- `read_expansion_case(case_dir)` — read back, typed re-parse, re-validate.
- Prove: byte-determinism across two builds; id uniqueness across **both** halves; every
  investment reference resolves to a component in the same document; sidecar has no orphans;
  `power_systems_type` values all name types present in the document.
- Build the real case into `cases/rts-expansion/` and report counts.

Mark the full-build tests `slow`, consistent with the operations suite.

---

## Julia tasks (JE1–JE6)

Mirror E1–E6 module-for-module against the Julia operations tutorial, once that exists.
Same stage order and the same sorted-where-sorted decisions, because the cross-language test
depends on identical id sequences.

**Julia-specific:**
- Use `InfrastructureTimeSeriesOpenAPIModels` and the 7-entry `[sources]` block (R15).
- Julia's `isfile`/`isdir` are case-insensitive on macOS, so the case-sensitive path resolution
  of R34 applies identically here.
- Julia style rules bind: no `isa` gates, `function … end` with explicit `return`, `iszero`,
  no `Union{Nothing,T}` sentinels.

### JE7 — Cross-language equivalence for the combined case

Extend the operations cross-language test to `cases/rts-expansion/`: equal per-bucket component
counts and equal `data_hash` sets across the two languages. **R19 still applies** — normalise
null-valued keys before comparing, since Python writes unset optionals as `null` while Julia
omits them.

---

## Documentation

Chapters under each project's `docs/`, continuing the operations numbering:
09 the investments schema and the combined document · 10 nodes, zones, existing fleet ·
11 supply and storage technologies (**and where the cost numbers come from**) ·
12 transport · 13 demand · 14 policy constraints · 15 building and validating the combined case.

**Chapter 11 carries the provenance table** — every field, whether it came from `RTS_inputs` or
from NREL ATB, and for the latter the exact source. That table is the honest core of this
example and should not be buried.

Audience is unchanged: no Sienna references beyond the package names, and no mention of the
private reference case.

---

## Open risk

The schema packages are being actively regenerated by their owner while this is built. One
enum member (`CommitmentModes.MARKET`) already vanished mid-campaign and broke 13 tests. The
investments types are newer and likelier to move than the operations ones. Every task should
treat a construction failure against the package as possible upstream drift first, and report
BLOCKED rather than working around it.
