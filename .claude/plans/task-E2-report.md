# Task E2 report — Existing devices and supply technologies (Python)

## Status: DONE

## What was built

New files (only these four; nothing under `python/src/rts_gmlc_case/` besides
them was touched):

- `python/src/rts_gmlc_case/investments/technologies.py` —
  `add_supply_technologies(doc, source, idx, inv_idx) -> dict[str, int]`
  plus two module constants: `POWER_SYSTEMS_TYPE_BY_CLASS` (the 9 candidate
  classes -> R39 PSY type name) and `FUEL_NAME_BY_CLASS` (the 5 thermal
  classes -> `Fuel` string, used to key `generation.FUEL_BY_SOURCE`). Mints
  one `SupplyTechnology` + one `ExistingDevices` supplemental attribute per
  class, iterated in sorted class-name order.
- `python/src/rts_gmlc_case/investments/costs.py` — `CAPITAL_COST_PER_MW`
  (dict, 9 classes -> USD/MW), `capital_cost_curve(tech_class) -> ValueCurve`,
  `financial_data_for(tech_class) -> TechnologyFinancialData`. Module
  docstring carries the honest-provenance framing R37 requires.
- `python/tests/test_investments_technologies.py` — 9 tests: dataset
  precondition (155 rows, all `IsExistUnit`), exact 9-class set (excluded
  set disjoint), R39 type assignment + same-document presence check,
  `ExistingDevices` counts against a fresh CSV group-by (not hardcoded,
  except three counts pinned from the brief's own table as an extra
  sanity check), association shape, `region` subset-of-real-zones +
  sortedness, `fuel` set only for thermal classes, `financial_data` fully
  populated, `doc.validate()`.
- `python/tests/test_investments_costs.py` — 5 tests: `CAPITAL_COST_PER_MW`
  key-set matches the candidate classes, values are a plausible
  order-of-magnitude ($100k-$10M/MW), `capital_cost_curve` is the expected
  flat `INPUT_OUTPUT`/`LINEAR` shape, `financial_data_for` yields 9 fully
  populated *distinct* instances, and a `-W error::UserWarning`-style
  no-warnings check on both builders directly.

## tech-class-inclusion reading

Used the literal 9-class reading given in the brief verbatim: `upv`,
`wind-ons` (supply-curve classes) + `gas-cc`, `gas-ct`, `o-g-s`,
`coalolduns`, `nuclear` (thermal) + `hydED`, `hydEND` (hydro). `distpv` and
`csp-ns` excluded (no supply curve, not thermal/hydro); `battery_4` excluded
(Task E3's `StorageTechnology`). Verified against the CSV: `gen_db["tech"]`
has exactly these 12 values, 9 of which became `SupplyTechnology`
components — no deviation, no ambiguity found here.

## R39 "type present in document" check: done in full, not deferred

`test_power_systems_type_is_an_r39_string_present_in_the_document` builds
`add_topology` + `add_generation` (the real operations stages, unmarked —
no time-series read, so it stays fast: the whole 14-test file runs in well
under a second) in the same `CaseDocument`, then runs
`add_investment_topology` + `add_supply_technologies` on top, and asserts
every `SupplyTechnology.power_systems_type` string is both a key in
`doc.document.components` and has `len(...) > 0` under it. This is the
brief's non-deferred option — **Task E6 does not need to pick up this
check**, it's already covered here. (`EnergyReservoirStorage`, R39's 4th
string, is not produced by any of E2's 9 classes; it will show up in Task
E3's storage-technology tests instead, against the same operations
document.)

## Capital-cost figures picked (USD/MW, flat linear)

| class | USD/MW | note |
|---|---|---|
| gas-cc | 1,150,000 | combined-cycle gas turbine |
| gas-ct | 850,000 | simple-cycle gas combustion turbine |
| o-g-s | 1,200,000 | **no ATB band given in the brief** — see below |
| coalolduns | 4,500,000 | old-unscrubbed-coal candidate slot |
| nuclear | 7,500,000 | — |
| hydED | 5,000,000 | existing-dam hydro upgrade/expansion |
| hydEND | 5,000,000 | non-dam (run-of-river) hydro |
| upv | 1,000,000 | utility-scale PV |
| wind-ons | 1,450,000 | onshore wind |

All 8 classes the brief gave a band for landed inside that band. `o-g-s`
is the one candidate class the brief's cost-figure list omits (it names
gas-cc/gas-ct/coalolduns/nuclear/hydED/hydEND/upv/wind-ons but not o-g-s).
I extrapolated $1.2M/MW — between `gas-ct`'s CT-based band and
`coalolduns`' STEAM-based band, since the source `o-g-s` class spans both
Unit Types (`CT`, `STEAM`) with `Fuel` always `Oil`. Flagging this as the
one figure that isn't a direct instantiation of a brief-given band, in
case a later task (or the user) wants a different number.

Financial data: one set of values applied to all 9 classes (brief allows
this) — `capital_recovery_period=25`, `technology_base_year=2030`,
`debt_fraction=0.5`, `debt_rate=0.045`, `return_on_equity=0.11`,
`tax_rate=0.21` — but a fresh `TechnologyFinancialData` instance is minted
per class (9 distinct objects, not one shared reference), matching "one
instance per class" literally.

## Design choices left to my judgment

- **`prime_mover_type` left explicit `None`, not the field's default.**
  Investigating why `add_supply_technologies` was producing a `UserWarning`
  on every `model_dump` uncovered an upstream `power_openapi_models` codegen
  bug: `SupplyTechnology.prime_mover_type`'s Pydantic field default is the
  bare string `"OT"`, not the enum member `PrimeMovers.OT` — this trips
  Pydantic's serializer warning path whenever the field is left at its
  default. This would have broken the brief's own required
  `-W error::UserWarning` gate. The brief's field-by-field instructions
  (power_systems_type, region, ExistingDevices, financial_data,
  capital_costs) never ask for `prime_mover_type` to be populated, and it
  isn't in the Verify checklist either, so I set it to an explicit `None`
  rather than working around the buggy default or fabricating a value —
  this also sidesteps a real ambiguity the brief doesn't resolve: `o-g-s`
  spans `Unit Type` `{CT, STEAM}`, so `generation.PRIME_MOVER_BY_UNIT_TYPE`
  can't give it one deterministic prime mover anyway. Not a fix to the
  upstream package (out of scope; `power_openapi_models` wasn't touched),
  just an explicit-None avoidance in this call site. Confirmed via
  `test_no_warnings_building_a_capital_cost_curve_or_financial_data` plus
  the full-suite `-W error::UserWarning -q` run below.
- **`region`'s "no class is zone-universal" note.** Read as "don't assume/
  hardcode universality" rather than "assert every class is a strict
  subset of all zones" — checking against the actual data, 6 of the 9
  classes (`coalolduns`, `gas-cc`, `gas-ct`, `hydED`, `o-g-s`, `upv`) *do*
  cover all 3 zones; only `nuclear` (1 zone), `hydEND` (1 zone), and
  `wind-ons` (2 zones) are proper subsets. My first test draft asserted a
  strict subset for every class and failed against real data — that was my
  own over-reading, not a brief requirement, and I corrected it to a
  non-strict subset check once the data disagreed.
- **`FUEL_NAME_BY_CLASS` keyed by tech class, not reusing `generation.py`'s
  `FUEL_BY_SOURCE` directly with a `Fuel`-column lookup per row.** Since
  `tech` -> `Fuel` is a clean many-to-one mapping (verified: every row of a
  class shares one `Fuel` value, `o-g-s` included), a class-level constant
  is simpler and self-documents which 5 classes are thermal, while still
  routing every actual enum lookup through the shared `FUEL_BY_SOURCE` dict
  (no redefinition of unit-type/fuel enum mappings, per the brief).
- **`idx: TopologyIndex` unused, `source: Path` used.** Mirrors E1's
  pattern for the parameter it didn't need (`del idx` with a docstring
  note) — no cross-check against the operations topology turned out to be
  necessary for this stage. `source` (here, `investments_source_dir()`'s
  return) *is* read, unlike in E1's `add_investment_topology`: the
  generator database lives under it.
- **Defensive `IsExistUnit`/empty-class assertions.** The brief states the
  155-row all-existing fact as already verified, and doesn't ask for a
  runtime check. Added one anyway (`add_supply_technologies` raises if any
  row has `IsExistUnit != True`, and if a class has zero rows) per this
  project's "never extend a silent-failure pattern" convention — a future
  dataset refresh that quietly introduces `IsExistUnit == False` rows or
  drops a class to zero should fail loudly here rather than silently
  produce a wrong or empty `ExistingDevices` list.

## Mismatch found: none

Cross-checked the brief's `tech -> (Unit Type, Fuel, row count)` table
against a fresh read of
`capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv`
(155 rows, `value_counts()` on `tech`): exact match, including the `o-g-s`
Unit-Type-spans-{CT,STEAM} exception and the 27/19/19 counts used as pinned
sanity checks in the test file. `SupplyTechnology`/`ExistingDevices`/
`TechnologyFinancialData`/`ValueCurve` field shapes read directly from
`power_openapi_models` match the brief's descriptions (confirmed
`SupplyTechnology.fuel` is `list[ThermalFuels] | None`, not a bare
`ThermalFuels`, so thermal classes' fuel value is wrapped in a
single-element list).

## Verification

- 9 `SupplyTechnology` components, named by exactly the 9 classes;
  `distpv`/`csp-ns`/`battery_4` absent (also confirmed present in the CSV's
  `tech` values, so their absence from the output is exclusion, not a
  missing-data artifact).
- Every `power_systems_type` matches the brief's per-class table and has
  `>0` components of that type in the same document (full pipeline, not
  deferred — see above).
- Every `ExistingDevices.existing_devices` list equals a fresh sorted
  `GEN UID` group-by on the CSV per class (27 for `gas-ct`, 19 for
  `hydED`/`o-g-s`, etc., all asserted against the CSV).
- Every `region` is a non-empty, sorted, real-zone-id subset.
- `financial_data` present, all 6 fields non-`None`, on every
  `SupplyTechnology`; `capital_costs` present on every one.
- `doc.validate()` passes (does not check `region` or supplemental
  attributes — same expected gap as E1's report).
- No `UserWarning`s from this stage (the `prime_mover_type` fix above was
  required to get here).

## Test commands run

```
cd python && uv run pytest tests/test_investments_technologies.py tests/test_investments_costs.py -v
```
→ **14 passed**, 0 failed.

```
cd python && uv run pytest -m "not slow" -v
```
→ **73 passed, 5 deselected**, 0 failed.

```
cd python && uv run pytest -m "not slow" -W error::UserWarning -q
```
→ **73 passed, 5 deselected**, 0 warnings surfaced as errors.

No git write commands were run (no `git add`, `git commit`, no staging).
`git status --porcelain -- python/` shows the whole `python/` tree as one
untracked entry (`?? python/`), consistent with E1's report — this
checkout has never tracked `python/` in git, so there is nothing to
distinguish staged vs. unstaged at the file level; no `git add` was ever
invoked either way.

## Files touched (all under `python/`, absolute paths)

- `/Users/jdlara/cache/psy6/SchemasTutorials/python/src/rts_gmlc_case/investments/technologies.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/src/rts_gmlc_case/investments/costs.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/tests/test_investments_technologies.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/tests/test_investments_costs.py` (new)

`julia/` and every other file under `python/src/rts_gmlc_case/` (including
`document.py`, `investments/topology.py`, `investments/data.py`) were left
untouched.
