# SDD ledger — plan: .claude/plans/2026-09-01-capacity-expansion-example-plan.md

Adapted process: no commits (CLAUDE.md forbids committing without explicit
ask; all git state stays unstaged in the main checkout). No git worktree
(nothing is committed, implementers run sequentially, one checkout is
enough). Controller reviews each task's diff directly via `git diff`
instead of dispatching a separate reviewer subagent per task.

Previous session's `<scratchpad>/CAMPAIGN-FACTS.md` and
`preflight-investments.md` (rulings R1-R39) no longer exist — session
scratchpads don't persist. R35-R39 are restated inline in the plan file.
R1-R34 are reconstructed from the already-built operations code
(`python/src/rts_gmlc_case/`, `julia/RTSGMLCCase/`), which the plan says
to mirror anyway.

## Pre-flight scan

- Raw data confirmed present: `data/RTS-investments/` (16-file subset) and
  `data/RTS-GMLC/` already downloaded. No fetch needed for E1's
  `investments_source_dir()` beyond wiring the existing local copy (or
  mirroring `data.py`'s pinned-download pattern if a fresh pull is ever
  needed).
- `power_openapi_models.investments.models` confirmed installed (editable,
  from `/Users/jdlara/cache/psy6/power-openapi-models/src`). Field lists
  for Node, Zone, TopologyMapping, ExistingDevices, SupplyTechnology,
  StorageTechnology, NodalAC/HVDCTransportTechnology, DemandRequirement,
  TechnologyFinancialData, PortfolioFinancialData, and the 6 policy types
  read directly from `models.py` (not guessed).
- `TopologyMapping` is a **supplemental attribute** (per
  `SiennaSchemas/Investments/Attributes/TopologyMapping.json`), not a
  regular bucketed component — it belongs in
  `SystemDocument.supplemental_attributes` (untyped dict list) plus one
  `SupplementalAttributeAssociation` row per (TopologyMapping, Zone) pair
  in `supplemental_attribute_associations`. `CaseDocument` (document.py)
  currently has no helper for supplemental attributes (only
  `add_service_association` exists for the service-association table) —
  E1 must add one. Ruling below.
- `Zone` (investments) has no node/bus list of its own; `Node` has no zone
  field either. The zone<->bus relationship lives entirely in the
  `TopologyMapping` supplemental attribute + its association row. E1's
  `add_investment_topology` must produce exactly that shape.
- No `Julia` operations equivalent check needed yet — `julia/RTSGMLCCase`
  already exists and mirrors the Python operations tutorial, so JE1-JE7
  are unblocked once Python E1-E6 land.

**Ruling:** Add `CaseDocument.add_supplemental_attribute(model, *,
component_id, component_type) -> int` to `document.py` as part of E1 (not
a separate task) — mints the attribute's id, appends the dumped model to
`document.supplemental_attributes`, appends a matching
`SupplementalAttributeAssociation(component_id=component_id,
component_type=component_type, attribute_id=<minted id>,
attribute_type=type(model).__name__)`, and returns the minted id. This is
new shared infrastructure the plan's E1 task implies but doesn't spell
out; it costs a slightly larger E1 diff if wrong, and is easy to undo
since no other stage depends on it yet.

## RESOLVED — session rate limit cleared 2026-09-02 ~1:31pm America/Denver

E6 was re-dispatched fresh per the plan below and completed successfully.
See its ledger entry under Tasks/Log. Note: the killed attempt had
*actually* written `document.py`'s `_MODEL_MODULES` fix and
`investments/build.py` before dying (contrary to this file's earlier
"no files were written yet" claim) — the retry found, verified, and
built on them rather than rewriting. **Lesson for future ledger entries:
don't assert what a killed agent did or didn't write without checking
`stat`/mtimes — a killed agent's own last message is not proof of what
landed on disk.**

## PAUSED — session rate limit (2026-09-02 ~10:18am America/Denver) [historical]

Task E6's implementer was killed mid-task by a hard session rate limit
("You've hit your session limit · resets 1:30pm (America/Denver)"). This
is an external quota wall, not a content or plan defect — E6's work so
far was reported as matching the brief exactly, right up to the point it
was about to write `investments/build.py`. **On resume: re-dispatch E6
fresh** (the failed agent's partial progress was not committed/saved —
no files were written yet per its own last message, so this is a clean
re-dispatch, not a resume-with-context situation) using the existing
brief at `.claude/plans/task-E6-brief.md`. Do not re-diagnose from
scratch — the brief is still correct and unchanged.

**Controller is scheduling wakeups (max 3600s each) until past ~1:30pm
America/Denver, then will retry E6.** If a future session picks this up
instead: just re-dispatch E6 per the brief; nothing else needs
re-verification.

## FINDING — the Julia operations tutorial is incomplete (discovered
## while prepping the JE-task briefs, before the rate limit hit)

`julia/RTSGMLCCase/src/RTSGMLCCase.jl` only `include`s `data.jl`,
`document.jl`, `topology.jl`, `branches.jl`, `generation.jl`. **Missing,
compared to the Python operations package
(`rts_gmlc_case`):** `demand.jl` (PowerLoad + OnlineReserve/reserves +
service associations), `sidecar.jl` (parquet writer), `timeseries.jl`
(time-series-pointer attachment), `build.jl` + a `build_rts.jl` CLI (the
combined driver). No `julia/cases/` or `cases/rts-julia/` exists either.

This matters because **the capacity-expansion plan's Julia tasks
(JE1-JE7) explicitly say "Mirror E1-E6 module-for-module against the
Julia operations tutorial, **once that exists**"** — it does not fully
exist yet. Specifically:
- JE1 (topology mirror) is unblocked today — Julia's `topology.jl`/
  `document.jl`/`data.jl` already exist and are complete enough to mirror
  E1 against.
- JE2 (supply technologies) is unblocked — only needs `generation.jl`
  (exists) for its `power_systems_type`-equivalent lookups.
- **JE3 (transport technologies)** needs `branches.jl` (exists, for the
  `Line`/`TwoTerminalGenericHVDCLine` `power_systems_type` convention) —
  unblocked.
- **JE4 (demand + time series) is BLOCKED**: it needs a Julia
  `timeseries.jl` (for the Layout-A CSV reader and
  `RESOLUTION_BY_SIMULATION`-equivalent) and `sidecar.jl` (for the
  parquet writer) — **neither exists yet.**
- **JE5 (policy)** is unblocked (only needs the investments technology
  ids from JE2/JE3's Julia ports).
- **JE6 (combined driver) is BLOCKED**: it needs a Julia `build.jl` (the
  operations driver) to extend — doesn't exist.
- **JE7 (cross-language equivalence)** is blocked transitively (needs
  JE6's combined build on both sides).

There's an existing plan for exactly this gap:
`.claude/plans/2026-08-28-julia-rts-tutorial-plan.md` (Tasks 6-9:
`demand.jl`, `sidecar.jl`, `timeseries.jl`, `build.jl` + `build_rts.jl`
CLI, plus Task 10's cross-language test and Task 11's docs). **Ruling:**
before dispatching JE4/JE6/JE7, first execute that plan's Tasks 6-9 (and,
per that plan, Task 10's cross-language test against the *operations*
cases `cases/rts-python/`/`cases/rts-julia/` — this is a separate,
already-planned deliverable this capacity-expansion plan assumes is
done). This is new scope this session inherited implicitly, not scope
the user asked to skip — flagging it plainly rather than silently
absorbing it or silently blocking JE4/JE6/JE7 forever. Sequencing once
capacity returns: **JE1 → JE2 → JE3 → JE5 (unblocked investments tasks)
in parallel-with-time with finishing the Julia operations tutorial's
missing Tasks 6-9, then JE4 → JE6 → JE7 once both lines land.**

## BLOCKED — sibling repo `PowerOpenAPIModels` is on an incompatible
## branch (2026-09-02 ~1:47pm America/Denver)

The JO task (finish the Julia operations tutorial) could not even
compile-check the *existing, already-working* `RTSGMLCCase` package.
Root cause: `/Users/jdlara/cache/psy6/PowerOpenAPIModels` (a plain
single-checkout sibling repo per this workspace's no-worktrees
convention) is currently checked out on branch `jd/openapi_deps_update`,
whose HEAD (commits timestamped 2026-09-02 10:19-12:38 — **this
morning, very recent**) migrated the whole codegen stack off the old
`OpenAPI.jl` (`OpenAPI.APIModel` supertype) onto a new native generator.
`RTSGMLCCase/src/document.jl` (which no task in this session may modify)
still declares against the old `OpenAPI.APIModel` shape, which no longer
exists on that branch. The implementer confirmed `PowerOpenAPIModels`'s
`main` branch (merge-base `0568d41`) still has the shape
`RTSGMLCCase` was built and tested against.

The implementer also regenerated `RTSGMLCCase`'s stale `Manifest.toml`
(backed up the original to
`.claude/plans/RTSGMLCCase-Manifest.toml.bak`) to fix an unrelated
resolve failure (`OpenAPI` pinned `0.2.9` in the old manifest vs.
`1.0.0` required via `[sources]`) — that regeneration is likely fine to
keep regardless of how the branch question resolves, but flagging it as
a real change made this session.

**Did not proceed further — correctly stopped rather than switching the
sibling repo's checkout unilaterally** (this affects a shared,
single-checkout repo that recent commit timestamps suggest may be
actively used by a concurrent session — a cross-repo side effect outside
this task's own scope, one of the standing stop conditions). Asked the
user how to proceed. **Do not touch `PowerOpenAPIModels`'s checkout
without explicit user direction.**

**RESOLVED 2026-09-02 ~1:53pm America/Denver:** user chose "check out
main temporarily." Verified `PowerOpenAPIModels` had a clean working
tree (no uncommitted changes) on `jd/openapi_deps_update` before
switching. Ran `git checkout main` there — now at `0568d41` (exactly the
confirmed merge-base). **Plan: restore `PowerOpenAPIModels` to
`jd/openapi_deps_update` once the Julia work (JO + JE1-7) is done**,
since that's the least disruptive default (returns the shared repo to
whatever state its own active work left it in) — this will be called out
again at that point in case the user wants it left on `main` instead.
**Next JO dispatch must first re-resolve `RTSGMLCCase`'s Julia
environment** (the previous JO attempt regenerated `Manifest.toml`
against `jd/openapi_deps_update`'s deps, backed up at
`.claude/plans/RTSGMLCCase-Manifest.toml.bak` — that regenerated
manifest is now stale too, since the branch changed again; don't assume
either the backup or the regenerated one is correct, just re-resolve
fresh against `main`'s shape and confirm `using RTSGMLCCase` compiles
before doing anything else).

**SECOND BLOCKER (resolved by ruling, ~2:03pm America/Denver):**
`PowerOpenAPIModels@main` (0568d41) resolved/compiled fine, but
`generation.jl`'s pre-existing `_build_thermal_standard` (not touched
this session before now) no longer matches current main's
`ThermalStandard` schema: `commitment_mode` field removed entirely,
`status` changed from a string enum to `Union{Nothing,Bool}`. This broke
all 73 thermal-unit construction, blocking any real Julia build.
**Ruling: authorized fixing `_build_thermal_standard`'s 3 fields**
(`status = true` not `"ONLINE"`; drop `commitment_mode`; add `must_run =
false`) as an exception to the "generation.jl gets only one small
addition" restriction — verified the exact current struct shape myself
first, this is a mechanical schema-drift fix to already-broken code, not
new logic. **Cost if wrong: low** — narrow, verified, 3-field change.

**Bigger finding, NOT blocking, but worth flagging to the user:**
Python's `power_openapi_models` (untouched, separate checkout) still
uses the OLD `ThermalStandard` shape (`status=OperationalStates.ONLINE`,
`commitment_mode=CommitmentModes.COMMITTED`, `must_run=False`) —
confirmed by reading `python/src/rts_gmlc_case/generation.py`. **The
Python and Julia OpenAPI packages have drifted out of sync** on this
schema (Julia's `main` is ahead). Ruled this does NOT block JE7 (the
capacity-expansion plan's cross-language check compares component
*counts* and time-series `data_hash` *sets*, not a full field-by-field
JSON diff — confirmed against the original Julia plan's Task 10 test
shape), so proceeding rather than stopping again. **Flag this to the
user in the final summary** as a real, independent finding outside this
plan's scope — the two OpenAPI packages need reconciling at some point,
just not by this session.

**THIRD BLOCKER (resolved by ruling, ~2:20pm America/Denver):**
`generation.jl`'s `GENERATOR_BUILDERS` only covers 4 of 12 `gen.csv`
`Unit Type`s (thermal: NUCLEAR/STEAM/CT/CC — 73 of 158 units), by its
own documented design ("a sibling task can add its five remaining
families"). That sibling task never landed. Confirmed via source-data
counts: **100% of `timeseries_pointers.csv`'s 264 `Category ==
"Generator"` rows target non-thermal units** (RTPV/HYDRO/PV/WIND/ROR/
CSP — zero target thermal), and 30 `reserves.csv`-eligible generators
(PV/WIND/CSP) are also non-thermal. Porting `demand.jl`/`timeseries.jl`
faithfully (raise-on-unmapped, per Python) against a thermal-only
`gen_ids` would make both non-functional and make the real build's
association counts (510 service / 282 time-series, Python's pinned
figures) unreachable. **Ruling: authorized implementing the remaining 8
unit-type builders in `generation.jl`** (`RenewableDispatch` for
WIND/PV/CSP, `RenewableNonDispatch` for RTPV, `HydroDispatch` for
HYDRO/ROR, `SynchronousCondenser`, `EnergyReservoirStorage` for
STORAGE) — mechanical port from the already-complete
`python/src/rts_gmlc_case/generation.py`, not new design. This is a
larger expansion of the "finish Julia operations tutorial" prerequisite
than originally scoped, but it's squarely within that same mandate
(reach Python parity) — the alternative (letting `demand.jl`/
`timeseries.jl` silently diverge from Python's raise-on-unmapped
behavior to route around the gap) would produce a materially incomplete,
non-parity deliverable, which is worse. **Cost if wrong:** more Julia
code to review, but it's a straight port of already-correct, tested
Python logic — low risk of a wrong *design*, ordinary risk of a porting
bug (caught by the same test suite this task already has to pass).

## PAUSED (again) — PowerOpenAPIModels's checkout changed underneath us
## (2026-09-02 ~4:22pm America/Denver)

JE5's implementer found `PowerOpenAPIModels` back on branch
`jd/openapi_deps_update` @ `cc658752` — **not** `main`/`0568d41`, where
the controller left it ~2.5 hours ago (~1:53pm). Controller independently
confirmed this directly (`git status`/`git rev-parse` in that repo,
clean working tree, same branch/commit JE5 reported). **This was not
caused by anything in this session** — nothing here touched that repo's
checkout since the 1:53pm switch. This strongly suggests concurrent,
independent activity in that shared repo (most plausibly the user
working on the `jd/openapi_deps_update` migration in another session),
exactly the risk flagged when the user first approved switching it.

Effect: `jd/openapi_deps_update`'s tree is fundamentally incompatible
with `RTSGMLCCase/src/document.jl` (frozen, unmodifiable this session) —
its `add!` function's type annotation is `PD.OpenAPI.APIModel`, a type
that doesn't exist on that branch at all (it migrated to a native
generator with no `OpenAPI.APIModel` supertype). This is the *original*
JO blocker, recurring. JE5's own new code and tests are unaffected (88/88
new assertions pass) — the only failures are 2 pre-existing
`test_build.jl` CLI-subprocess tests that fail to precompile fresh
against the current (wrong-branch) checkout.

**Not resolving this unilaterally a second time** — repeatedly flipping
a shared repo's branch back against what looks like the user's own
live, concurrent work would be presumptuous and could disrupt it. Asking
the user how to proceed before dispatching JE6 (which needs a working
build to verify its 6 required proofs against a real `cases/rts-julia-
expansion/` build, not just compiling source).

## Tasks

- [x] E1 — dataset module, nodes, zones, topology mapping
- [x] E2 — existing devices and supply technologies
- [x] E3 — storage and transport technologies
- [x] E4 — demand requirement and its time series
- [x] E5 — policy constraints
- [x] E6 — combined driver, round-trip, validation, build `cases/rts-expansion/`
- [x] JO6-9 — finish the Julia OPERATIONS tutorial (demand.jl,
      sidecar.jl, timeseries.jl, build.jl+build_rts.jl CLI) per
      `.claude/plans/2026-08-28-julia-rts-tutorial-plan.md` Tasks 6-9 —
      prerequisite for JE4/JE6/JE7, discovered mid-session (see FINDING
      above)
- [x] JE1 — Julia mirror of E1 (topology) — unblocked now
- [x] JE2 — Julia mirror of E2 (supply technologies) — unblocked now
- [x] JE3 — Julia mirror of E3 (storage/transport) — unblocked now
- [x] JE4 — Julia mirror of E4 (demand+timeseries) — blocked on JO6-9
- [~] JE5 — Julia mirror of E5 (policy) — unblocked now — logic complete
      and passing (88/88 new assertions), 2 pre-existing/environmental
      failures found (see PAUSED note below), not marked [x] until the
      environment question is resolved
- [ ] JE6 — Julia mirror of E6 (combined driver) — blocked on JO6-9, JE1-5
- [ ] JE7 — cross-language equivalence for the combined case — blocked on JE6
- [ ] Docs — chapters 09-15 in both projects' `docs/`

## Log

- **Task JO6-9: complete — JULIA OPERATIONS TUTORIAL NOW FULLY AT PARITY
  WITH PYTHON.** New: `demand.jl`, `sidecar.jl`, `timeseries.jl`,
  `build.jl`, `build_rts.jl`. `generation.jl` expanded from 4/12 to
  12/12 unit-type builders (the scope-expansion ruling above) plus the
  `ThermalStandard` schema-drift fix. Real case built:
  `cases/rts-julia/system.json` + `timeseries/` (146 parquet files).
  Controller independently verified: `julia --project=test
  test/runtests.jl` → 3659/3659 passed; component counts, 146
  `data_hash` values (byte-for-byte, not just count), and 510
  `service_associations` all **exactly match** `cases/rts-python/`.
  Manifests regenerated fresh against `PowerOpenAPIModels@main`
  (0568d41). Reports: `task-JO-report.md`.
- **Cross-package version drift, flagged not fixed:** Julia's
  `PowerOpenAPIModels@main` and Python's `power_openapi_models` have
  diverged on `ThermalStandard`'s exact fields (Julia ahead — see
  ruling above). Does not affect this plan's own cross-language checks
  (count + hash equality, confirmed above), but the two packages should
  be reconciled by their owner at some point. **Include this in the
  final summary to the user.**
- **Task JE1: complete.** New: `investments_data.jl`
  (`investments_source_dir`), `investments_topology.jl`
  (`InvestmentTopologyIndex`, `add_investment_topology!`) — flat under
  `src/`, no subdirectory (matches package convention). 73 Node, 3 Zone,
  3 TopologyMapping confirmed. `_normalize_bustype` reused with zero
  shim (Julia's flat module namespace makes this easier than Python's
  private-import workaround). Controller re-ran `julia --project=test
  test/runtests.jl` independently: 3795/3795 passed (up from 3659), zero
  regressions. Code review: clean. Reports: `task-JE1-report.md`.
- **Task JE2: complete.** New: `investments_costs.jl`
  (`CAPITAL_COST_PER_MW`, `flat_linear_value_curve`,
  `capital_cost_curve`, `financial_data_for` — same 9 figures as
  Python), `investments_technologies.jl` (`add_supply_technologies!`, 9
  `SupplyTechnology` + 9 `ExistingDevices`, same classes/counts as
  Python). `ValueCurve`'s nested-oneOf construction confirmed
  (`PD.ValueCurve(PD.InputOutputCurve(; function_data =
  PD.InputOutputCurveFunctionData(PD.LinearFunctionData(...))))`) — no
  `prime_mover_type` warning workaround needed in Julia (plain string
  default, no warning system to trip). Controller re-ran `julia
  --project=test test/runtests.jl` independently: 4216/4216 passed (up
  from 3795), zero regressions. Code review: clean. Reports:
  `task-JE2-report.md`.
- **Task JE3: complete.** New: `investments_storage.jl`
  (`add_storage_technologies!`, 1 `StorageTechnology` "battery_4"),
  `investments_transport.jl` (`add_transport_technologies!`, 108
  `NodalACTransportTechnology` + 1 `NodalHVDCTransportTechnology`, same
  duplicate-pair-summing ruling as Python). Extended
  `investments_costs.jl` with battery cost helpers +
  `transport_financial_data`. `InOut(; in=, out=)` confirmed to compile
  as-is (no `var"in"` escaping needed). Controller re-ran `julia
  --project=test test/runtests.jl` independently: 5283/5283 passed (up
  from 4216), zero regressions. Code review: clean. Reports:
  `task-JE3-report.md`.
- **Task JE4: complete.** New: `investments_demand.jl`
  (`add_demand_requirements!`, 3 `DemandRequirement`, same
  `VALUE_OF_LOST_LOAD=9000.0` as Python, PT1H time series reused
  directly from `timeseries.jl`'s `read_profile`/
  `RESOLUTION_BY_SIMULATION`). One subtlety found and handled correctly:
  the new file's `include` had to go after `sidecar.jl`/`timeseries.jl`
  (for the `SidecarWriter` type annotation to resolve at include-time),
  not right next to JE1's files as a literal brief reading might
  suggest — implementer reasoned through Julia's include-time type
  resolution rather than guessing. Controller re-ran `julia
  --project=test test/runtests.jl` independently: 5344/5344 passed (up
  from 5283), zero regressions. Code review: clean. Reports:
  `task-JE4-report.md`.

- Task E1: complete. New: `investments/__init__.py`, `investments/data.py`
  (`investments_source_dir()` — validates the local 16-file dataset,
  does not download; no verified pinned URL/checksum was available this
  session, left as an explicit TODO comment for a future session),
  `investments/topology.py` (`add_investment_topology`,
  `InvestmentTopologyIndex`), `tests/test_investments_data.py`,
  `tests/test_investments_topology.py`,
  `tests/test_document_supplemental_attribute.py`. Extended:
  `document.py` with `CaseDocument.add_supplemental_attribute` (the E1
  ruling above). 73 Node, 3 Zone, 3 TopologyMapping (as supplemental
  attributes) confirmed. Controller re-ran `uv run pytest -m "not slow"
  -q` independently: 59 passed, 5 deselected — matches the implementer's
  report. Code review: clean, no fix round needed. Reports:
  `task-E1-report.md`.
- Task E2: complete. New: `investments/technologies.py`
  (`add_supply_technologies`, `POWER_SYSTEMS_TYPE_BY_CLASS`,
  `FUEL_NAME_BY_CLASS`), `investments/costs.py` (`CAPITAL_COST_PER_MW`,
  `capital_cost_curve`, `financial_data_for`),
  `tests/test_investments_technologies.py`,
  `tests/test_investments_costs.py`. 9 `SupplyTechnology` candidates
  (`upv`, `wind-ons`, `gas-cc`, `gas-ct`, `o-g-s`, `coalolduns`,
  `nuclear`, `hydED`, `hydEND`); `distpv`/`csp-ns`/`battery_4` correctly
  excluded. R39 type-presence check done in full against a real
  operations+investments document (not deferred to E6). Capital costs
  are illustrative NREL-ATB-order-of-magnitude figures, clearly labelled
  as unverified this session (R37). Controller re-ran `uv run pytest -m
  "not slow" -q` independently: 73 passed, 5 deselected — matches.
  Code review: clean, no fix round needed. Reports: `task-E2-report.md`.
- **Ruling carried forward:** E2 found and worked around an upstream
  `power_openapi_models` codegen quirk — `SupplyTechnology.prime_mover_type`
  defaults to the bare string `"OT"` instead of `PrimeMovers.OT`, which
  trips a pydantic serializer `UserWarning` on `model_dump` whenever left
  at its default. E2 sidesteps this by setting `prime_mover_type=None`
  explicitly at its one call site (nothing in E2 needs a populated prime
  mover, and `o-g-s` has no single deterministic one anyway). **Any later
  task that builds a `SupplyTechnology`, `StorageTechnology`, or similar
  investments component with a `prime_mover_type` field must do the same
  (explicit value or explicit `None`, never rely on the field default)**
  or the `-W error::UserWarning` gate will fail. This is a RULE ZERO
  upstream-package issue, not something to patch in
  `power-openapi-models` under this plan.
- Task E3: complete. New: `investments/storage.py`
  (`add_storage_technologies`, 1 `StorageTechnology` "battery_4" + 1
  `ExistingDevices`), `investments/transport.py`
  (`add_transport_technologies`, 108 `NodalACTransportTechnology` + 1
  `NodalHVDCTransportTechnology`). Extended: `investments/costs.py`
  (`flat_linear_value_curve`, battery cost helpers,
  `transport_financial_data`). Controller re-ran `uv run pytest -m "not
  slow" -q` independently: 105 passed, 5 deselected — matches. Code
  review: clean, no fix round needed. Reports: `task-E3-report.md`.
- **Ruling: AC transport duplicate-pair resolution (load-bearing for
  E6/JE6/JE7).** `transmission_capacity_init_AC_rts_nodal.csv` has 120
  rows but 108 distinct `(From_Bus, To_Bus)` pairs (12 pairs duplicated,
  identical `MW_f0`/`MW_r0`, no circuit-id column). Ruled: **one
  `NodalACTransportTechnology` per unique pair (108 total), summing
  `MW_f0` across duplicates** (parallel circuits combine into one
  corridor's existing capacity). **The Julia mirror (JE3) must reproduce
  this exact same 108-count and summing rule**, or the cross-language
  equivalence test (JE7) will fail on component counts. Cost if wrong:
  a mismatched Julia count in JE3/JE7, caught by that task's own
  cross-language check — not silently propagated further, since JE7
  explicitly compares counts.
- **Ruling: transport `power_systems_type` values.** Not specified by
  the plan text for `NodalACTransportTechnology`/
  `NodalHVDCTransportTechnology` (required schema fields). Set to
  `"Line"` (AC) and `"TwoTerminalGenericHVDCLine"` (HVDC), matching what
  `rts_gmlc_case.branches` actually builds for the analogous operations
  devices (same R39 "exact PSY type name this campaign emits" principle
  E2 used). Cost if wrong: a docs/provenance-table correction later; no
  downstream task reads these two specific strings today.
- Task E4: complete. New: `investments/demand.py`
  (`add_demand_requirements`, 3 `DemandRequirement` one per zone, PT1H
  time series reused directly from operations `timeseries.py`'s
  `read_profile`/`RESOLUTION_BY_SIMULATION`). `power_systems_type =
  "PowerLoad"` confirmed against operations `demand.py`.
  `value_of_lost_load = 9000.0` USD/MWh, illustrative, explicitly not a
  citation of `scalars.csv`'s `cost_dropped_load`. Controller re-ran `uv
  run pytest -m "not slow" -q` independently: 110 passed, 5 deselected —
  matches. Code review: clean, no fix round needed. Reports:
  `task-E4-report.md`.
- Task E5: complete. New: `investments/policy.py`
  (`add_policy_constraints`, 9 illustrative policy components: 4
  `CarbonCaps` + 1 each of `CarbonTax`, `CapacityReserveMargin`,
  `EnergyShareRequirements`, `MinimumCapacityRequirements`,
  `MaximumCapacityRequirements`). Extended: `document.py` with
  `CaseDocument.append_requirement` (the reference mechanism: policies
  attach via the `requirements` list already on
  `SupplyTechnology`/`StorageTechnology`, since none of the 6 policy
  types has its own zone/technology field). Full scenario is the
  controller's design (carbon cap trajectory, RPS, coal phase-out, wind
  floor) — see `task-E5-brief.md`/`task-E5-report.md` for exact
  targeting. Controller re-ran `uv run pytest -m "not slow" -q`
  independently: 123 passed, 5 deselected — matches. Code review: clean,
  no fix round needed. Reports: `task-E5-report.md`.
- **Ruling: `append_requirement` is new shared `CaseDocument`
  infrastructure**, same category as E1's `add_supplemental_attribute` —
  mutates an already-added component's dumped dict in place, raises
  loudly (`KeyError`/`ValueError`) on an unknown type/id rather than
  silently no-opping. No downstream task should need a third variant of
  this pattern; if one seems needed, check whether `append_requirement`
  already covers it first.
- **Task E6: complete — PYTHON SIDE (E1-E6) FULLY DONE.** New:
  `investments/build.py` (`build_expansion_case`, `read_expansion_case`),
  `build_expansion.py` CLI. Extended: `document.py`'s `_MODEL_MODULES`
  to include `"investments"` (required for `typed_components()` to
  re-parse any investments type on read-back — without it,
  `read_expansion_case` raises `KeyError`). Real case built:
  `cases/rts-expansion/system.json` (773KB) + `timeseries/` (149
  parquet files). **768 total components** (561 operations + 207
  investments): full breakdown in `task-E6-report.md`. 285
  `time_series_associations`, 510 `service_associations`, 13
  `supplemental_attributes`. All 6 required proofs (byte-determinism,
  id-uniqueness-across-both-halves, reference-resolution, no sidecar
  orphans, R39 type-presence, round-trip typed re-parse) implemented
  and passing. Controller re-ran `uv run pytest -m "not slow" -q`
  independently: 124 passed, 12 deselected; `uv run pytest
  tests/test_investments_build.py -q`: 8 passed; confirmed
  `cases/rts-expansion/` on disk with 768 components, 285 associations.
  Code review: clean, no fix round needed. `cases/rts-python/`
  confirmed untouched. Reports: `task-E6-report.md`.
- **Open item (not a ruling, just unresolved):** `investments/data.py`
  has no real pinned download — it only validates the dataset already
  present on disk. If this example is ever meant to work from a clean
  checkout without the data pre-staged, someone needs to identify the
  authoritative source URL for the 16-file RTS-investments subset and
  wire up the same checksum-verified download `rts_gmlc_case.data.py`
  does. Flagging for the user, not blocking further tasks (data is
  already staged in this checkout).
