# Task E3 report — Storage and transport technologies (Python)

## Status: DONE

## What was built

New files:

- `python/src/rts_gmlc_case/investments/storage.py` —
  `add_storage_technologies(doc, source, inv_idx) -> dict[str, int]`. One
  `StorageTechnology` (class `"battery_4"`) + one `ExistingDevices`
  supplemental attribute.
- `python/src/rts_gmlc_case/investments/transport.py` —
  `add_transport_technologies(doc, source, inv_idx) -> tuple[dict, dict]`
  (`ac_id_by_bus_pair`, `hvdc_id_by_bus_pair`, each keyed by
  `(start_bus_number, end_bus_number)`). 108 `NodalACTransportTechnology` +
  1 `NodalHVDCTransportTechnology`.
- `python/tests/test_investments_storage.py` — 13 tests.
- `python/tests/test_investments_transport.py` — 13 tests.

Extended (only file touched besides the two new modules, as instructed):

- `python/src/rts_gmlc_case/investments/costs.py` — added
  `flat_linear_value_curve(proportional_term)` (the flat
  `INPUT_OUTPUT`/`LINEAR` builder generalized out of `capital_cost_curve`,
  which is now a thin wrapper over it — same output, existing E2 tests
  still pass unchanged), `BATTERY_CAPITAL_COST_PER_MW_CHARGE`/
  `_DISCHARGE`/`BATTERY_CAPITAL_COST_PER_MWH_ENERGY` +
  `battery_capital_cost_curves()`, `battery_operation_cost()`, and
  `transport_financial_data()`. Module docstring extended (not
  re-disclaimed) to route the new figures through the same illustrative-
  vs-sourced framing.
- `python/tests/test_investments_costs.py` — added 7 tests covering the
  new helpers (this is the "extend whichever cost test file already
  covers it" option from the brief).

## Duplicate-AC-pair resolution and resulting count (load-bearing for E6)

Verified independently (fresh pandas read, not trusting the brief's
numbers blindly): `transmission_capacity_init_AC_rts_nodal.csv` has 120
data rows, 108 distinct `(From_Bus, To_Bus)` pairs, 12 pairs each appearing
as two rows with identical `MW_f0`/`MW_r0` (e.g. `b115,b121` twice at
`MW_f0=MW_r0=500`), no circuit-id column. `MW_f0 == MW_r0` holds on every
row (no exceptions). The cost file's 108 rows are exactly the capacity
file's 108 unique pairs, one-to-one, no gaps.

Used the controller's suggested reading: **one `NodalACTransportTechnology`
per unique pair (108 total)**, `capacity_limits.max` = the **sum** of
`MW_f0` across duplicate rows for that pair (parallel circuits on the same
corridor combining into one investable corridor's existing capacity). For
the 12 duplicated pairs this doubles the single-row figure (e.g.
`b115→b121` becomes 1000 MW, not 500) — confirmed by
`test_duplicate_pair_capacity_is_summed`, which checks both a duplicated
pair (`AC_115_121` → 1000.0) and a non-duplicated one (`AC_101_102` →
175.0, unchanged) against the real document.

**Resulting count: 108 `NodalACTransportTechnology` components.** Asserted
against a fresh CSV `groupby(...).ngroups` read, not a hardcoded literal,
in `test_nodal_ac_transport_technology_count_matches_a_fresh_csv_read`
(which also pins `== 108` as an explicit sanity check).

I did not find a reason to prefer a per-circuit (2-per-pair) reading
instead — nothing in `NodalACTransportTechnology`'s field shape (a single
`capacity_limits: MinMax`, no circuit multiplicity field) supports building
two components for one corridor, and the brief's own framing ("parallel
circuits... combine into one investable corridor") matches how an
investment-planning transport candidate is normally modeled: one candidate
per corridor with its aggregate existing capacity as the floor of the
capacity range.

## StorageTechnology capacity fields: what was populated vs. left `None`, and why

- `capacity_limits_charge = MinMax(min=0.0, max=50.0)` and
  `capacity_limits_discharge = MinMax(min=0.0, max=50.0)` — both populated
  from the one dataset-backed number available, `cap` (50.0 MW), read from
  the CSV row rather than hardcoded. `cap` is a power (MW) figure, so it
  maps naturally onto the charge/discharge power-capacity ceilings, not the
  energy-capacity one.
- `capacity_limits_energy = None` — **left `None` deliberately.** No energy
  (MWh) capacity figure exists anywhere in `battery_4`'s generator-database
  row or in the two storage-duration files (both empty — see below); I did
  not fabricate one (e.g. by assuming a 4-hour duration and multiplying
  `cap * 4`), since the brief explicitly warns against inventing an
  energy-capacity number that isn't in the dataset.
- `duration_limits = None` — verified (not assumed) that both
  `storagedata/storage_duration_pshdata.csv` and
  `storagedata/storinmaxfrac.csv` are header-only: `len(pd.read_csv(...))
  == 0` for both, asserted in
  `test_both_duration_csvs_have_zero_data_rows`. A code comment in
  `storage.py`'s module docstring states this reasoning; a future dataset
  refresh that adds real rows will fail that test and surface the gap
  rather than silently leaving `duration_limits` wrong.

## Battery capital-cost figures picked (USD/MW or USD/MWh, flat linear)

Illustrative, NREL-ATB-order-of-magnitude, same "no live ATB pull this
session" framing as E2's `CAPITAL_COST_PER_MW`:

| field | value | note |
|---|---|---|
| `capital_costs_charge` | $200,000/MW | charging power-capacity leg |
| `capital_costs_discharge` | $200,000/MW | discharging power-capacity leg |
| `capital_costs_energy` | $300,000/MWh | energy-capacity (cell) leg |

Chosen so a 4-hour duration reconstructs to ≈$1.6M/MW total installed cost
(`200k×2 + 300k×4 = 1.6M`), in the same ballpark as NREL ATB's ~$1,590/kW
2030-moderate 4-hour utility-scale Li-ion figure. `operation_costs` is an
all-zero `StorageCost` (`fixed`/`shut_down`/`start_up`/
`energy_shortage_cost`/`energy_surplus_cost` all `0.0`) — no dataset or ATB
figure backs a nonzero value, and this mirrors the exact all-zero
convention `generation._build_energy_reservoir_storage` already uses for
the operations-side `EnergyReservoirStorage`'s `operation_cost`.
`financial_data` reuses `financial_data_for("battery_4")` unchanged (that
helper already ignores its argument and is uniform across every caller, so
no new helper was needed for this field).

## Transport capital costs and financial data: genuinely sourced, not illustrative

- `capital_costs` on every `NodalACTransportTechnology`/
  `NodalHVDCTransportTechnology` is a flat linear curve built directly from
  each row's real `USD2004perMW` figure (joined by `(r, rr) ==
  (From_Bus, To_Bus)` for AC, and the single matching row for HVDC) — **2004
  USD, no inflation adjustment applied.** This is stated as a limitation in
  both the module docstring and inline, not silently corrected.
  `test_ac_capital_costs_are_dataset_sourced_not_illustrative` and
  `test_hvdc_capital_cost_matches_the_dc_cost_file` check every value
  against a fresh CSV read.
- `financial_data.capital_recovery_period == 40` on every transport
  component, genuinely sourced from `scalars.csv`'s `trans_crp` row
  (confirmed via `grep`: `trans_crp,40,--years-- transmission capital
  recovery period...`). The other 5 `TechnologyFinancialData` fields have
  no transmission-specific source and are illustrative (same values as
  `financial_data_for`), via the new `transport_financial_data()` helper.
- `resistance`/`reactance`/`voltage`/`unit_size`
  (`NodalACTransportTechnology`) and `line_loss`
  (`NodalHVDCTransportTechnology`) are left at their schema defaults
  (`0.0`/`None`) — no dataset field backs any of them at this stage.

## Design choices left to my judgment (flagging, not hiding)

- **`available=True` required on all three new component types.** This
  surprised me: unlike `SupplyTechnology.available` (optional, defaults
  `None`, left unset by E2), `StorageTechnology.available`,
  `NodalACTransportTechnology.available`, and
  `NodalHVDCTransportTechnology.available` are all *required* fields
  (`PydanticUndefined` default, no default value) — omitting them raised a
  pydantic `ValidationError` on first run, not a warning. Set `True` on all
  three (these are all active/investable candidates), verified by the full
  test suite constructing them successfully.
- **`power_systems_type` for transport technologies is this module's own
  choice, not brief-specified.** The brief's Part B field lists never
  mention `power_systems_type` for `NodalACTransportTechnology`/
  `NodalHVDCTransportTechnology` (unlike Part A's explicit
  `"EnergyReservoirStorage"` for storage), but it's a required string
  field on both models. Followed the same R39 convention E2 established
  (the exact PSY type name the *operations* campaign builds for the
  analogous device): `"Line"` for AC (confirmed `rts_gmlc_case.branches`
  builds every AC branch as `Line`, never `MonitoredLine`, by reading its
  source directly) and `"TwoTerminalGenericHVDCLine"` for HVDC (same
  file). Flagging in case a different R39 string was intended here.
- **`prime_mover_type=PrimeMovers.BA` set explicitly on
  `StorageTechnology`**, per the ledger's carried-forward ruling and the
  brief's own instruction — confirmed via `-W error::UserWarning` that this
  is warning-clean. Unlike `SupplyTechnology`'s `o-g-s` case (no single
  deterministic prime mover existed), `BA` here is not just
  warning-avoidance: this candidate always models a battery, so it is also
  the semantically correct value.
- **Reused `GENERATOR_DATABASE` and `financial_data_for` from
  `technologies.py`/`costs.py` by import, not by duplicating the
  constant/logic.** No modification to those files' contents was needed —
  only new imports were added at each new file's top, which the brief's
  "only these files" restriction covers (I did not edit `technologies.py`
  itself).
- **Naming**: `NodalACTransportTechnology.name` is `f"AC_{start_bus}_
  {end_bus}"` (numeric bus ids, not the `bXXX` label) and HVDC is
  `f"HVDC_{start_bus}_{end_bus}"` — arbitrary, the brief doesn't specify a
  naming convention for these components.
- **`doc.validate()` does not check `start_node`/`end_node`/`region`
  references** (same gap E1/E2's reports already noted for `bus`/`region`-
  shaped fields — `_REFERENCE_FIELDS` in `document.py` doesn't include
  them). I did not extend `document.py` (out of scope per the brief's file
  restriction) — instead, "every AC/HVDC start_node/end_node resolves to a
  real Node id" is verified by a dedicated test
  (`test_every_ac_and_hvdc_start_end_node_resolves_to_a_real_node_id`)
  against the real `Node` id set, independent of `validate()`.

## Mismatch found: none

Cross-checked every count and figure the brief stated against a fresh read
of the source CSVs (battery row count/fields, both duration CSVs' row
counts, AC capacity/cost row counts and duplicate structure, HVDC
capacity/cost single-row match, `scalars.csv`'s `trans_crp` value) — all
matched exactly, no deviation found.

## Verification (against the brief's Verify checklist)

- Exactly 1 `StorageTechnology`, `power_systems_type ==
  "EnergyReservoirStorage"`, 1 `ExistingDevices` attribute with
  `existing_devices == ["313_STORAGE_1"]` — confirmed.
- `duration_limits` is `None` on the `StorageTechnology`, with a test
  confirming both duration CSVs have zero data rows — confirmed.
- `NodalACTransportTechnology` count == 108, asserted against a fresh CSV
  read (`groupby(...).ngroups`), not a hardcoded literal (also pinned as
  `== 108` as a sanity check) — confirmed.
- Every AC/HVDC `start_node`/`end_node` resolves to a real Node id —
  confirmed via dedicated test (see judgment-calls section on
  `doc.validate()`'s gap).
- 1 `NodalHVDCTransportTechnology`, `capacity_limits.max == 100.0` —
  confirmed.
- Every transport `financial_data.capital_recovery_period == 40` —
  confirmed for all 108 AC + 1 HVDC.
- `doc.validate()` still passes — confirmed (storage test suite and
  transport test suite each have a `test_validate_passes`).
- No `UserWarning`s under `-W error::UserWarning` from this stage's model
  construction — confirmed (`test_no_warnings_building_storage_technologies`,
  `test_no_warnings_building_transport_technologies`, plus the full-suite
  gated run below).

## Test commands run

```
cd python && uv run pytest tests/test_investments_storage.py tests/test_investments_transport.py -v
```
→ **26 passed**, 0 failed.

```
cd python && uv run pytest -m "not slow" -q
```
→ **105 passed, 5 deselected**, 0 failed. Reconciles exactly: E2 left 73
passed; this task adds 13 (`test_investments_storage.py`) + 13
(`test_investments_transport.py`) + 6 new tests appended to
`test_investments_costs.py` (its 5 pre-existing tests are unchanged) = 32
new tests; 73 + 32 = 105.

```
cd python && uv run pytest -m "not slow" -W error::UserWarning -q
```
→ **105 passed, 5 deselected**, 0 warnings surfaced as errors.

No git write commands were run (no `git add`, `git commit`, no staging).
`git status --porcelain` shows the whole `python/` tree as one untracked
entry (`?? python/`), same as E1/E2 — nothing to distinguish staged vs.
unstaged at the file level; no `git add` was invoked either way. Confirmed
via `find src/rts_gmlc_case/investments tests -newer ...` that only the
six intended files were modified this session (`storage.py`, `transport.py`,
`costs.py`, `test_investments_storage.py`, `test_investments_transport.py`,
`test_investments_costs.py`) — `topology.py`, `data.py`,
`technologies.py`, and every other test file were untouched.

## Files touched (all under `python/`, absolute paths)

- `/Users/jdlara/cache/psy6/SchemasTutorials/python/src/rts_gmlc_case/investments/storage.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/src/rts_gmlc_case/investments/transport.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/tests/test_investments_storage.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/tests/test_investments_transport.py` (new)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/src/rts_gmlc_case/investments/costs.py` (extended)
- `/Users/jdlara/cache/psy6/SchemasTutorials/python/tests/test_investments_costs.py` (extended)

`julia/` and every other file under `python/src/rts_gmlc_case/` (including
`document.py`, `investments/topology.py`, `investments/data.py`,
`investments/technologies.py`) were left untouched.
