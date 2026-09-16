# Task E5 — Policy constraints (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md`. Progress
ledger: `.claude/plans/2026-09-01-capacity-expansion-progress.md` — Tasks
E1-E4 are done; read their ledger entries before starting.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`julia/`. This task DOES need one small, targeted addition to
`document.py` (see below) — that is the only existing file you may
modify besides the new ones.

## The plan's exact words for this task

*"Six types, all illustrative (R37): `CarbonCaps`, `CarbonTax`,
`CapacityReserveMargin`, `EnergyShareRequirements`,
`MinimumCapacityRequirements`, `MaximumCapacityRequirements`. One module,
one docstring stating plainly that no value here comes from `RTS_inputs`
and that these are a worked scenario a reader is expected to replace.
Values should be plausible for RTS scale rather than round placeholders —
an 80%-by-2050 carbon cap trajectory, a reserve margin in the usual
10-15% band — so the example demonstrates a realistic problem shape."
Verify: "each type constructs and validates; every zone/technology
reference resolves."*

## The reference mechanism (not spelled out by the plan — read this
## carefully, it's the load-bearing part of this task)

None of the 6 policy model classes has a `region` or `technology`
field — check `power_openapi_models.investments.models` yourself to
confirm. The plan's Verify bullet ("every zone/technology reference
resolves") can only mean one thing: policies attach to the technologies
they constrain through **the `requirements: list[int] | None` field that
already exists on `SupplyTechnology`, `StorageTechnology`,
`NodalACTransportTechnology`, `NodalHVDCTransportTechnology`, and
`DemandRequirement`** ("List of requirement IDs associated with the
component.") — every one of those was built by E2/E3/E4 with
`requirements=[]` (the schema default). This task must retroactively
append each policy component's minted id into the `requirements` list of
every technology it constrains.

**This needs a `CaseDocument` helper that doesn't exist yet — add it as
part of this task:**

```python
def append_requirement(
    self, *, component_type: str, component_id: int, requirement_id: int
) -> None:
    """Append `requirement_id` to the `requirements` list of the
    component `component_id` inside `document.components[component_type]`.
    Raises `KeyError`/`ValueError` if the type or id isn't found — never
    silently no-ops on a bad reference.
    """
```

It must find the matching dict inside `self.document.components[component_type]`
by its `"id"` key and mutate its `"requirements"` list in place (append,
don't replace — a component could in principle gain more than one
requirement, though this task's scenario below only ever adds one per
component). Raise a clear error (naming the type and id) if the type
bucket or the specific id isn't found — this project's "never extend a
silent-failure pattern" convention applies here as much as anywhere else.
Add a focused unit test for this helper alongside your policy tests (or
in a small `test_document_append_requirement.py`, your call).

## The illustrative scenario (the controller's design — use these exact
## numbers and targets; this is not a judgment call, it's the brief)

One module, `investments/policy.py`. Module docstring: state plainly that
none of these values comes from `RTS_inputs`, and that this is a worked
scenario a reader is expected to replace with their own policy design.

Build these 9 policy components, then wire `requirements` on the named
targets via `append_requirement`:

1. **`CarbonCaps` x4 — an 80%-by-2050 trajectory**, one component per
   checkpoint year:
   - `target_year=2025, max_mtons=8.0`
   - `target_year=2030, max_mtons=6.5`
   - `target_year=2040, max_mtons=3.5`
   - `target_year=2050, max_mtons=1.6` (80% below the 2025 figure)
   - Leave `max_tons_mwh` at its schema default (don't set both rate and
     absolute forms).
   - **Targets (all 4 components):** the 4 fossil-thermal
     `SupplyTechnology` candidates — `gas-cc`, `gas-ct`, `o-g-s`,
     `coalolduns` (i.e. E2's 9 candidates minus `nuclear`, `hydED`,
     `hydEND`, `upv`, `wind-ons`, which don't burn carbon fuel). Use
     E2's `add_supply_technologies` return value (class name -> id map)
     to look these up — don't re-derive ids from scratch.
2. **`CarbonTax` x1** — `target_year=2030, tax_dollars_per_ton=15.0`.
   **Targets:** the same 4 fossil-thermal classes as `CarbonCaps`.
3. **`CapacityReserveMargin` x1** — `target_year=2030,
   capacity_reserve_fraction=0.13` (13%, inside the plan's stated
   10-15% band). **Targets:** every `SupplyTechnology` (all 9) plus the
   one `StorageTechnology` — everything that contributes firm/dispatchable
   capacity system-wide (10 components total).
4. **`EnergyShareRequirements` x1** — `target_year=2030,
   generation_fraction_requirement=0.30` (30%). **Targets:** the 2
   renewable `SupplyTechnology` candidates, `upv` and `wind-ons`.
5. **`MinimumCapacityRequirements` x1** — `target_year=2035,
   min_capacity_mw=200.0`. **Target:** `wind-ons` only (an RPS-like
   capacity floor).
6. **`MaximumCapacityRequirements` x1** — `target_year=2035,
   max_capacity_mw=0.0`. **Target:** `coalolduns` only (a coal-phase-out
   ceiling on new candidate capacity — this is a cap on the *investable
   candidate*, not existing units, which is exactly what this component
   type represents).

Every policy component: `available=True`, `name` a short human-readable
label (e.g. `"Carbon cap 2025"`, `"RPS 2030"`, `"Coal phase-out 2035"` —
your call on exact wording).

## `add_policy_constraints(doc, supply_ids, storage_ids) -> dict[str, list[int]]`

- `supply_ids`: E2's `add_supply_technologies` return (`dict[str, int]`,
  class name -> id).
- `storage_ids`: E3's `add_storage_technologies` return (`dict[str, int]`,
  class name -> id; currently just `{"battery_4": <id>}`).
- Build each policy component via `doc.add_component`, then call
  `doc.append_requirement(component_type="SupplyTechnology", ...)` (or
  `"StorageTechnology"`) for every (policy, target) pair in the scenario
  above.
- Return a mapping from policy-type name to the list of minted ids (e.g.
  `{"CarbonCaps": [id1, id2, id3, id4], "CarbonTax": [id5], ...}`) — later
  tasks/tests may want this.

## Verify

- Exactly 9 policy components total, 4 `CarbonCaps` + 1 each of the other
  5 types.
- Every numeric value matches the scenario table above exactly.
- Every named target technology's `requirements` list contains exactly
  the policy id(s) that should apply to it per the scenario (e.g.
  `gas-cc`'s `SupplyTechnology.requirements` contains both the matching
  `CarbonCaps` ids... wait, all 4 `CarbonCaps` ids apply to every
  fossil-thermal class — so `gas-cc.requirements` should end up with 4
  `CarbonCaps` ids + 1 `CarbonTax` id + 1 `CapacityReserveMargin` id = 6
  entries total; `upv.requirements` should have 1
  `CapacityReserveMargin` id + 1 `EnergyShareRequirements` id = 2 entries;
  `wind-ons.requirements` should have `CapacityReserveMargin` +
  `EnergyShareRequirements` + `MinimumCapacityRequirements` = 3 entries;
  `coalolduns.requirements` should have 4 `CarbonCaps` + 1 `CarbonTax` + 1
  `CapacityReserveMargin` + 1 `MaximumCapacityRequirements` = 7 entries;
  `nuclear`/`hydED`/`hydEND.requirements` should each have just the 1
  `CapacityReserveMargin` id; the 1 `StorageTechnology` should have just
  the 1 `CapacityReserveMargin` id). Write your test to compute this
  expectation programmatically from the scenario table, not by re-typing
  these counts as magic numbers.
- Every `requirements` entry resolves to a real policy component id that
  exists in the document.
- `doc.validate()` still passes (note: `validate()`'s reference-resolution
  pass does not check `requirements` — same documented gap as `region`/
  `bus` in earlier tasks' reports; add a dedicated test for the
  requirements-resolve check instead, same pattern E3 used for
  `start_node`/`end_node`).
- No `UserWarning`s under `-W error::UserWarning`.

## Report

Write your full report to
`.claude/plans/task-E5-report.md`. Since this task needs both E2's and
E3's outputs, your own tests should build a small local `CaseDocument`
that runs `add_investment_topology` -> `add_supply_technologies` ->
`add_storage_technologies` -> `add_policy_constraints`, not just this
task's module in isolation. Run `cd python && uv run pytest
tests/test_investments_policy.py -v` (plus the `append_requirement` test
file if separate), then `uv run pytest -m "not slow"` for the full
non-slow suite, then `uv run pytest -m "not slow" -W error::UserWarning
-q`. Reply with only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED,
the exact commands and pass counts, and a one-line pointer to the report
file.

If anything here is ambiguous in a way that's load-bearing for Task E6
(the combined-document build), ask before guessing rather than after.