# Task JE5 report — Julia mirror of E5: policy constraints

## Summary

Ported `python/src/rts_gmlc_case/investments/policy.py` into
`julia/RTSGMLCCase/src/investments_policy.jl`, with test coverage in
`julia/RTSGMLCCase/test/test_investments_policy.jl`. All new tests pass. The full suite has
2 pre-existing failures unrelated to this task — see "Pre-existing failure" below.

## Files changed

- **New:** `julia/RTSGMLCCase/src/investments_policy.jl` — `add_policy_constraints!` plus the
  scenario constants (`FOSSIL_THERMAL_CLASSES`, `RENEWABLE_CLASSES`, `CARBON_CAP_TRAJECTORY`,
  `CARBON_TAX_YEAR`/`_DOLLARS_PER_TON`, `CAPACITY_RESERVE_MARGIN_YEAR`/`_FRACTION`,
  `ENERGY_SHARE_YEAR`/`_FRACTION`, `MINIMUM_CAPACITY_YEAR`/`_MW`/`_CLASS`,
  `MAXIMUM_CAPACITY_YEAR`/`_MW`/`_CLASS`) and the `_find_component`/`_add_requirement!` helpers
  from the brief.
- **New:** `julia/RTSGMLCCase/test/test_investments_policy.jl` — 7 testsets, 88 assertions.
- **Edited:** `julia/RTSGMLCCase/src/RTSGMLCCase.jl` — added
  `include("investments_policy.jl")` after `investments_transport.jl` (JE2/JE3's includes).
- **Edited:** `julia/RTSGMLCCase/test/runtests.jl` — added
  `include("test_investments_policy.jl")` after `test_investments_transport.jl`.

No other file was touched. `python/` was not touched. PowerOpenAPIModels's checkout was not
touched.

## What `add_policy_constraints!` does

Signature: `add_policy_constraints!(doc::PD.SystemDocument, supply_ids::Dict{String,Int},
storage_ids::Dict{String,Int}) -> Dict{String,Vector{Int}}`.

Mints, in this order (matching Python's `add_policy_constraints` and its test's
`POLICY_TYPES_IN_PROCESSING_ORDER`):

1. **`CarbonCaps` x4** — `(2025, 8.0)`, `(2030, 6.5)`, `(2040, 3.5)`, `(2050, 1.6)`
   (`target_year`, `max_mtons`), each wired to `gas-cc`/`gas-ct`/`o-g-s`/`coalolduns`.
2. **`CarbonTax` x1** — `2030`, `$15.0`/ton, same 4 targets.
3. **`CapacityReserveMargin` x1** — `2030`, `0.13`, wired to all 9 `SupplyTechnology` +
   the 1 `StorageTechnology` (iterated in sorted class-name order for determinism).
4. **`EnergyShareRequirements` x1** — `2030`, `0.30`, wired to `upv`/`wind-ons`.
5. **`MinimumCapacityRequirements` x1** — `2035`, `200.0` MW, wired to `wind-ons` only.
6. **`MaximumCapacityRequirements` x1** — `2035`, `0.0` MW, wired to `coalolduns` only.

Every value matches the brief's scenario table verbatim. `available = true` on every component;
names mirror Python's (`"Carbon cap 2025"`, `"Carbon tax 2030"`, `"Capacity reserve margin
2030"`, `"RPS 2030"`, `"Wind capacity floor 2035"`, `"Coal phase-out 2035"`).

Per the brief's note on Julia's simpler reference mechanism: `_find_component` looks up a live
component by type name and id from `doc`, and `_add_requirement!` does
`push!(_find_component(...).requirements, requirement_id)` — since `requirements` defaults to
the already-allocated `Int64[]` on both `SupplyTechnology` and `StorageTechnology` (confirmed
in `model_SupplyTechnology.jl`/`model_StorageTechnology.jl` under
`PowerOpenAPIModels/PowerInvestmentsOpenAPIModels.jl/src/models/`), no `isnothing` guard or
wrapper type was needed — `push!` mutates the document in place directly.

## Test coverage

`test_investments_policy.jl` builds the full JE1→JE4 chain (topology, generation, investment
topology, supply technologies, storage technologies) then calls `add_policy_constraints!`,
mirroring `test_investments_storage.jl`'s `_build_storage_technologies` pattern. 7 testsets:

1. Exactly 9 policy components (4 `CarbonCaps` + 1 each of the other 5 types).
2. `add_policy_constraints!`'s return value's ids all resolve to real components, with the
   right per-type counts.
3. `CarbonCaps` trajectory values match the scenario table exactly, including the
   80%-by-2050 check (`cap_2050 == cap_2025 * 0.2`).
4. `CarbonTax`/`CapacityReserveMargin`/`EnergyShareRequirements` values, including the
   10–15% reserve-margin band check.
5. `MinimumCapacityRequirements`/`MaximumCapacityRequirements` values.
6. Every `SupplyTechnology`/`StorageTechnology`'s `requirements` list matches an
   **programmatically computed** expectation: a declarative `{policy_type =>
   target_class_set}` table (`_scenario_targets`) plus `_expected_requirements`, which walks
   `POLICY_TYPES_IN_PROCESSING_ORDER` and appends each type's minted id(s) when the tech class
   is a target — no re-typed magic-number counts. This is the test that pins the brief's worked
   table (`gas-cc`/`gas-ct`/`o-g-s` = 6, `coalolduns` = 7, `hydED`/`hydEND`/`nuclear`/
   `battery_4` = 1, `upv` = 2, `wind-ons` = 3), derived rather than hardcoded.
7. Every `requirements` entry across all `SupplyTechnology`/`StorageTechnology` components
   resolves to a real component id somewhere in the document (`validate_document` does not
   check this field, same documented gap as `region`/`bus`/`start_node`/`end_node` in earlier
   stages — this is the dedicated check for it).
8. `PowerOpenAPIModels.validate_document(doc)` passes on the full built document.

One Python test was **not** ported: `test_no_warnings_building_policy_constraints`
(`warnings.simplefilter("error")` around the call). This is a pydantic-model-construction idiom
with no Julia analog in this codebase — none of the OpenAPI-generated Julia model constructors
emit `@warn`, and no other test file in this Julia port uses a "no warnings" pattern, so there
was nothing to mirror.

## Verification

- `julia --project=. -e 'using RTSGMLCCase'` — compiles clean.
- `julia --project=test test/runtests.jl` — **5430 passed, 2 failed, 5432 total** (up from the
  stated 5344-test baseline by the 88 new assertions this task added). All of this task's new
  testsets pass in full:
  - `exactly 9 policy components: 4 carbon caps plus 1 each of 5 others` — 6/6
  - `add_policy_constraints! return value matches component counts` — 16/16
  - `carbon caps trajectory values match the scenario table` — 10/10
  - `carbon tax, capacity reserve margin, and energy share values` — 7/7
  - `minimum and maximum capacity requirement values` — 4/4
  - `every supply and storage technology carries exactly the expected requirements` — 10/10
  - `every requirements entry resolves to a real policy component id` — 35/35

## Pre-existing failure (not caused by this task) — please read

The 2 failures are both inside the **existing** `test_build.jl` testset `"cli reports usage
error without output dir"` (line 111–112), which spawns a fresh subprocess:
`julia --project=$package_root build_rts.jl` and asserts it exits with code 2 and prints
"usage". Instead, that subprocess now fails to precompile with:

```
ArgumentError: Package InfrastructureCoreOpenAPIModels does not have Base64 in its dependencies
```

(and similarly for JSON, across PowerInvestmentsOpenAPIModels, PowerDynamicsOpenAPIModels,
PowerOperationsOpenAPIModels, InfrastructureTimeSeriesOpenAPIModels, PowerCoreOpenAPIModels,
PowerOpenAPIModels, and finally RTSGMLCCase itself.)

**Root cause, verified independently of any of my changes:**

1. `julia/RTSGMLCCase/Manifest.toml` and `test/Manifest.toml` both record
   `PowerInvestmentsOpenAPIModels`'s deps as `["HTTP", "InfrastructureCoreOpenAPIModels",
   "JSON3", "OpenAPI", "PowerCoreOpenAPIModels"]` (and similarly incomplete/wrong entries for
   its siblings).
2. The actual dev-path checkout's `Project.toml` for that package (and several siblings) lists
   `Base64, Dates, HTTP, InfrastructureCoreOpenAPIModels, JSON, OpenAPI, PowerCoreOpenAPIModels,
   UUIDs` — `JSON` not `JSON3`, plus `Base64`/`Dates`/`UUIDs` the Manifest doesn't know about —
   and its `src/*.jl` does `using HTTP, JSON, OpenAPI, Base64, Dates, UUIDs`.
3. **`PowerOpenAPIModels`'s checkout is currently on branch `jd/openapi_deps_update` at commit
   `cc658752`** (`git -C /Users/jdlara/cache/psy6/PowerOpenAPIModels rev-parse --abbrev-ref
   HEAD` / `rev-parse HEAD`), **not** `main` at `0568d41` as the task brief stated. Its most
   recent commit there is "Migrate codegen to OpenAPI.jl 1.0's native pure-Julia generator" —
   consistent with the deps drift above. I did not check this out; per the hard rules I did not
   touch it.
4. Reproduced directly and deterministically, independent of RTSGMLCCase's own source:
   `julia --project=. -e 'using Pkg; Pkg.precompile()'` and `julia --project=. build_rts.jl`
   both fail the same way, on `PowerOpenAPIModels`'s own direct dependencies, before
   `RTSGMLCCase` itself is even reached.

Because RTSGMLCCase's `Manifest.toml`/`test/Manifest.toml` haven't been re-resolved (`Pkg.resolve()`)
against this checkout state, any process that needs to freshly precompile these packages hits
the mismatch. A process that already has a valid pre-existing compiled-cache slot for the exact
same environment closure does not re-trigger the check (which is why most of the suite — running
in one already-warm `--project=test` process — passed cleanly); this only surfaces when a fresh
subprocess (as `test_build.jl`'s CLI test spawns, and as I did directly to confirm) needs to
precompile from scratch.

**This is unrelated to JE5's content** — it lives entirely in `test_build.jl` (an existing
JE-earlier test, not modified here), and the failure is inside `PowerOpenAPIModels`'s own
dependency chain, before `RTSGMLCCase` is reached at all.

**I did not attempt to fix this** — doing so would require either checking out
`PowerOpenAPIModels`'s `main`/`0568d41` (forbidden — "Do not change PowerOpenAPIModels's git
branch/checkout") or running `Pkg.resolve()`, which rewrites `Manifest.toml`/`test/Manifest.toml`
(forbidden — "Do not modify any existing file except the two include list appends"). Flagging
this now since the brief's assumption about the checkout state is materially wrong and will
block JE6/JE7 the same way.

## One incidental note on this session

While diagnosing the above, I ran two duplicate background `julia --project=test
test/runtests.jl` invocations concurrently and then used `pkill`/`kill -9` to clean up the
duplicate — that only killed processes I had just started in this session; no file was written
to or otherwise affected by it beyond the depot's own Julia compiled-cache directories under
`~/.julia/compiled/`, which are regenerable build artifacts, not source. No git operations were
run in any repo, and no destructive operation touched anything inside `julia/RTSGMLCCase/`,
`python/`, or `PowerOpenAPIModels/`.
