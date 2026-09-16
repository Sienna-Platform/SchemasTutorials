# Task E5 report — Policy constraints (Python)

## Summary

Implemented the illustrative policy-constraints stage exactly per the
brief (`.claude/plans/task-E5-brief.md`): one new module
`python/src/rts_gmlc_case/investments/policy.py` building 9 policy
components (4 `CarbonCaps` + 1 each of `CarbonTax`,
`CapacityReserveMargin`, `EnergyShareRequirements`,
`MinimumCapacityRequirements`, `MaximumCapacityRequirements`), wired to
their target `SupplyTechnology`/`StorageTechnology` candidates via a new
`CaseDocument.append_requirement` helper added to `document.py`.

## Files touched

- **Modified** (only existing file touched, as the brief allows):
  `python/src/rts_gmlc_case/document.py` — added
  `CaseDocument.append_requirement(*, component_type, component_id,
  requirement_id) -> None`. Looks up `self.document.components[component_type]`
  (raises `KeyError` naming the type if the bucket doesn't exist), finds
  the item whose `"id"` matches `component_id` (raises `ValueError` naming
  the type and id if no match), and appends `requirement_id` to that
  item's `"requirements"` list in place. Also added one line to the
  module's top docstring listing the new helper alongside
  `add_supplemental_attribute`.
- **New:** `python/src/rts_gmlc_case/investments/policy.py` —
  `add_policy_constraints(doc, supply_ids, storage_ids) -> dict[str, list[int]]`
  plus the scenario constants (`FOSSIL_THERMAL_CLASSES`,
  `RENEWABLE_CLASSES`, `CARBON_CAP_TRAJECTORY`, `CARBON_TAX_YEAR`,
  `CARBON_TAX_DOLLARS_PER_TON`, `CAPACITY_RESERVE_MARGIN_YEAR`,
  `CAPACITY_RESERVE_FRACTION`, `ENERGY_SHARE_YEAR`,
  `ENERGY_SHARE_FRACTION`, `MINIMUM_CAPACITY_YEAR`,
  `MINIMUM_CAPACITY_MW`, `MINIMUM_CAPACITY_CLASS`,
  `MAXIMUM_CAPACITY_YEAR`, `MAXIMUM_CAPACITY_MW`,
  `MAXIMUM_CAPACITY_CLASS`). Module docstring states plainly that no
  value comes from `RTS_inputs` and that the scenario is a worked
  example a reader should replace, and documents the `requirements`-field
  reference mechanism in the same detail as the brief.
- **New:** `python/tests/test_investments_policy.py` — 9 tests. Builds a
  local `CaseDocument` through the full chain
  `add_topology` -> `add_generation` -> `add_investment_topology` ->
  `add_supply_technologies` -> `add_storage_technologies` ->
  `add_policy_constraints` (mirrors E3/E4's `_build` helper pattern).
  Covers: exact component counts (4+1+1+1+1+1=9), the `add_policy_constraints`
  return-value shape, every numeric value against the scenario table,
  and — per the brief's explicit instruction — a
  programmatically-computed expected `requirements` list per technology
  class, built from a declarative `{policy_type: target_class_set}`
  table (`_scenario_targets`) and the fixed policy-processing order
  (`POLICY_TYPES_IN_PROCESSING_ORDER`), rather than re-typed magic
  numbers. Also: a dedicated "every `requirements` entry resolves to a
  real component id" test (since `validate()` doesn't check
  `requirements`), a `doc.validate()` pass test, and a
  `-W error::UserWarning` smoke test.
- **New:** `python/tests/test_document_append_requirement.py` — 4 focused
  unit tests for the new helper: appends in place, appends a second id
  without replacing the first, raises `KeyError` for an unknown component
  type, raises `ValueError` for an unknown component id within a known
  type.

## Scenario values (verbatim from the brief, confirmed via test)

- `CarbonCaps`: 2025/8.0, 2030/6.5, 2040/3.5, 2050/1.6 Mt (1.6 is exactly
  80% below 8.0). `max_tons_mwh` left at schema default (not set).
  Targets: `gas-cc`, `gas-ct`, `o-g-s`, `coalolduns`.
- `CarbonTax`: 2030, $15.0/ton. Same 4 fossil-thermal targets.
- `CapacityReserveMargin`: 2030, 0.13 (13%, inside the 10-15% band).
  Targets: all 9 `SupplyTechnology` + the 1 `StorageTechnology` (10
  components).
- `EnergyShareRequirements`: 2030, 0.30 (30%). Targets: `upv`, `wind-ons`.
- `MinimumCapacityRequirements`: 2035, 200.0 MW. Target: `wind-ons` only.
- `MaximumCapacityRequirements`: 2035, 0.0 MW. Target: `coalolduns` only.

Every component: `available=True`, a short human-readable `name` (e.g.
`"Carbon cap 2025"`, `"Carbon tax 2030"`, `"Capacity reserve margin
2030"`, `"RPS 2030"`, `"Wind capacity floor 2035"`, `"Coal phase-out
2035"`).

## Verified requirement-list shapes (printed from a live build, ids
elided as `[...]` for readability — full run confirms the brief's exact
per-class counts)

```
coalolduns   7  (4 CarbonCaps + 1 CarbonTax + 1 CapacityReserveMargin + 1 MaximumCapacityRequirements)
gas-cc       6  (4 CarbonCaps + 1 CarbonTax + 1 CapacityReserveMargin)
gas-ct       6  (same shape as gas-cc)
o-g-s        6  (same shape as gas-cc)
hydED        1  (CapacityReserveMargin only)
hydEND       1  (CapacityReserveMargin only)
nuclear      1  (CapacityReserveMargin only)
upv          2  (CapacityReserveMargin + EnergyShareRequirements)
wind-ons     3  (CapacityReserveMargin + EnergyShareRequirements + MinimumCapacityRequirements)
battery_4    1  (CapacityReserveMargin only)
```

This matches the brief's Verify section exactly, including per-class
counts and which policy types are represented.

## Test commands and results (this session)

```
uv run pytest tests/test_investments_policy.py tests/test_document_append_requirement.py -v
  -> 13 passed

uv run pytest -m "not slow" -q
  -> 123 passed, 5 deselected
  (110 passed before this task per the progress ledger's E4 entry; +13
  new tests here = 123, consistent)

uv run pytest -m "not slow" -W error::UserWarning -q
  -> 123 passed, 5 deselected
```

No `UserWarning`s raised anywhere in the non-slow suite with this task's
code included.

## Notes / things worth flagging

- `SupplyTechnology.financial_data` and `TechnologyFinancialData`'s 6
  sub-fields are all schema-required (not defaulted) — the
  `append_requirement` unit test's minimal `SupplyTechnology` fixture
  needed a real `financial_data_for(...)` value (reused from
  `investments/costs.py`) rather than a bare stub, or pydantic validation
  fails at construction time. Not a policy.py concern (policy.py never
  constructs a `SupplyTechnology`), just a fixture-correctness note for
  whoever reads this test later.
- `doc.append_requirement` mutates the dumped dict in
  `self.document.components[component_type]` in place (appends to the
  existing `"requirements"` list already present from `add_component`'s
  `model_dump`), matching the brief's "append, don't replace" instruction
  and its warning against silent no-ops on bad references.
- Did not touch `julia/`, did not run any `git add`/`git commit`, working
  tree left unstaged.

## Ambiguities encountered

None that were load-bearing enough to stop and ask. The brief's "the
reference mechanism" section, its exact scenario table, and its Verify
section's worked-out per-class counts (gas-cc = 6, upv = 2, etc.) were
unambiguous and are reproduced exactly by the implementation, confirmed
both by the live print-out above and by the test suite's
programmatically-computed expectations.
