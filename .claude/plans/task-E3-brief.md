# Task E3 — Storage and transport technologies (Python)

Part of the RTS capacity-expansion example. Full plan:
`.claude/plans/2026-09-01-capacity-expansion-example-plan.md`. Progress
ledger: `.claude/plans/2026-09-01-capacity-expansion-progress.md` — Tasks
E1 and E2 are done; read their ledger entries and
`.claude/plans/task-E1-report.md` / `task-E2-report.md` before starting.

**Read the ledger's "Ruling carried forward" note about
`prime_mover_type`.** `SupplyTechnology`'s (and, per the same upstream
codegen quirk, likely other investments models') `prime_mover_type` field
defaults to the bare string `"OT"` instead of the enum member
`PrimeMovers.OT`, which trips a pydantic `UserWarning` on `model_dump`
unless the field is set explicitly (a real value, or explicit `None`).
`StorageTechnology` has this same field — set it explicitly to
`PrimeMovers.BA` (battery) rather than leaving the default, and confirm
with `-W error::UserWarning` that this and every other field you touch is
warning-clean.

**Do not run `git add`, `git commit`, or any git write.** Do not touch
`julia/`. Do not modify any file under `python/src/rts_gmlc_case/` other
than the two new files plus one extension to `investments/costs.py`
(below) — if you find you need to change anything else, stop and report
NEEDS_CONTEXT rather than guessing.

## What E1/E2 already gave you

- `investments/topology.py`: `InvestmentTopologyIndex` with
  `node_id_by_bus_number: dict[int, int]`, `zone_id_by_name`,
  `zone_id_by_bus_number`.
- `investments/data.py`: `investments_source_dir() -> Path`.
- `investments/technologies.py`: the `add_supply_technologies` pattern —
  mirror its structure/style (module docstring citing the plan, sorted
  iteration, explicit-`None`/explicit-value on every enum field with a
  buggy default, `add_supplemental_attribute` usage) for this task's two
  new stages.
- `investments/costs.py`: `CAPITAL_COST_PER_MW`, `capital_cost_curve`,
  `financial_data_for` (uniform financial data across all 9 supply
  classes). **Extend this module** (don't create a second costs module —
  R37 wants the entire external-cost surface in one auditable place) with
  whatever storage/transport capital-cost and financial-data helpers this
  task needs, following its existing docstring's provenance framing.
- `python/src/rts_gmlc_case/generation.py`: read
  `_build_energy_reservoir_storage` (around line 365) for the exact,
  already-used convention for `Storage Roundtrip Efficiency` ->
  `InOut` efficiency: `math.sqrt(float(row["Storage Roundtrip
  Efficiency"]) / 100.0)`, split evenly across the two legs — **reuse this
  exact formula** for `StorageTechnology.efficiency`, don't reinvent it.
  `generation.py`'s `StorageTech.OTHER_CHEM` choice for battery storage is
  also worth reusing for `StorageTechnology.storage_tech` (same field
  meaning, different field name: `storage_technology_type` in the
  operations model vs `storage_tech` in the investments model).

## New files

- `python/src/rts_gmlc_case/investments/storage.py`
- `python/src/rts_gmlc_case/investments/transport.py`
- `python/tests/test_investments_storage.py`
- `python/tests/test_investments_transport.py`
- (extend) `python/src/rts_gmlc_case/investments/costs.py`
- (extend) whichever cost test file already covers it, or a new one —
  your call

## Part A — `StorageTechnology`

Data: `capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv`
(same file E2 read, under `investments_source_dir()`). Exactly **one**
`tech == "battery_4"` row exists (`GEN UID` `"313_STORAGE_1"`, `Bus ID`
313, `cap` 50.0 MW, `Storage Roundtrip Efficiency` 85). Build **one**
`StorageTechnology` candidate:

- `power_systems_type = "EnergyReservoirStorage"` (R39's 4th string — not
  produced by any of E2's 9 `SupplyTechnology` classes, so this is where
  it first appears; if E6 or E2's test asserts "every R39 string appears
  somewhere", this is what makes that true for `EnergyReservoirStorage`).
- `storage_tech = StorageTech.OTHER_CHEM`.
- `prime_mover_type = PrimeMovers.BA` (explicit — see the warning note
  above).
- `region`: same pattern as E2 — the zone id(s) (via
  `InvestmentTopologyIndex.zone_id_by_bus_number`) where `battery_4`
  devices sit (just zone containing bus 313 here, but write it as a
  general zone-set computation, not a hardcoded single value, in case a
  future dataset refresh adds more battery rows).
- `efficiency`: `InOut(**{"in": leg, "out": leg})` with `leg =
  math.sqrt(85.0 / 100.0)` via the reused formula above — read the actual
  value from the CSV row, don't hardcode `85.0`.
- Capacity fields (`capacity_limits_charge`, `capacity_limits_discharge`,
  `capacity_limits_energy`) — the plan says *"capacity from the dataset
  where present"*. `cap` (50.0 MW) is the one dataset-backed number
  available; use it as the natural power-capacity ceiling (e.g.
  `MinMax(min=0.0, max=50.0)` on the charge/discharge power limits — your
  call on exactly which of the three MinMax fields it's most correct to
  populate with it, given `cap` is a power (MW) figure, not an energy
  (MWh) one). Don't invent an energy-capacity (MWh) number that isn't in
  the dataset — leave `capacity_limits_energy` `None` if nothing backs it,
  and say so in your report rather than silently fabricating one.
- `duration_limits: MinMax | None` — **R37: leave this `None` and say why**
  in a code comment. Verify first: both
  `storagedata/storage_duration_pshdata.csv` and
  `storagedata/storinmaxfrac.csv` contain **zero data rows** (header only —
  confirmed by the controller: each file is exactly 1 line). Add a test
  asserting this (`len(pd.read_csv(...)) == 0`) so a future dataset
  refresh that adds real duration data is caught rather than silently
  leaving `duration_limits` wrong.
- `capital_costs_energy`, `capital_costs_charge`, `capital_costs_discharge`,
  `operation_costs`, `financial_data` — external/illustrative (R37), from
  the extended `costs.py`. Pick plausible order-of-magnitude figures for
  a 4-hour lithium-ion battery (illustrative NREL ATB-style,
  clearly labelled, same honesty framing `costs.py`'s docstring already
  states — don't re-state the whole disclaimer, just extend the existing
  one if a new figure needs its own provenance note).
- One `ExistingDevices` supplemental attribute (same mechanism as E2),
  `existing_devices = ["313_STORAGE_1"]`, attached to this
  `StorageTechnology`'s id with `component_type="StorageTechnology"`.

`add_storage_technologies(doc, source, inv_idx) -> dict[str, int]` (name/
signature your call; return class-name -> id, mirroring E2's return
shape, even though there's only one class today).

## Part B — Transport technologies

### `NodalACTransportTechnology`

Data: `transmission/transmission_capacity_init_AC_rts_nodal.csv` (120
rows: `interface`, `From_Bus`, `To_Bus`, `MW_f0`, `MW_r0` — bus ids in
`bXXX` form, e.g. `b101`; strip the leading `b` to get the numeric bus id
that joins to E1's `node_id_by_bus_number`) and
`transmission/transmission_distance_cost_500kVac_nodal.csv` (108 rows:
`r`, `rr`, `length_miles`, `USD2004perMW` — same `bXXX` join key on `r`/`rr`
matching `From_Bus`/`To_Bus`).

**Known wrinkle, verified by the controller — read before writing the
join:** the capacity file has 120 rows but only 108 distinct
`(From_Bus, To_Bus)` pairs — 12 pairs each appear as **two exactly
identical rows** (same `MW_f0`/`MW_r0`), e.g. `b115,b121` appears twice
with `MW_f0=MW_r0=500` both times. There is no circuit-id column in this
file to distinguish them (unlike the operations `branch.csv`'s
`Circuit`). The cost file has exactly the 108 unique pairs, one row each,
and its pair-set matches the capacity file's unique-pair-set exactly (no
pairs on one side only). Every capacity-file row's `MW_f0 == MW_r0`
(verified, no exceptions).

Resolve this by building **one `NodalACTransportTechnology` per unique
`(From_Bus, To_Bus)` pair (108 total)**, summing `MW_f0` across duplicate
rows for that pair (representing combined parallel-circuit capacity) —
this is the controller's suggested reading (parallel circuits on the same
corridor combine into one investable corridor's existing capacity), not
a value pulled from the brief's plan text, since the plan doesn't
mention this wrinkle. If you find a reason this is wrong (e.g. a
per-circuit interpretation makes more sense given how `NodalACTransportTechnology`
is meant to be used elsewhere), say so in your report and use your
judgment — but 108 is the number Task E6's cross-language check will
need to match against the eventual Julia build, so whatever you choose,
make it deterministic and state the resulting count clearly.

Fields:
- `start_node`/`end_node`: Node ids via `node_id_by_bus_number`, from
  `From_Bus`/`To_Bus` (strip `b`).
- `capacity_limits = MinMax(min=0.0, max=<summed MW_f0>)`.
- `capital_costs`: a flat linear `ValueCurve` (same shape
  `costs.py.capital_cost_curve` already builds — reuse that helper's
  pattern, or generalize it, your call) from `USD2004perMW`, joined by
  `(r, rr)` == `(From_Bus, To_Bus)`. This is a genuinely **dataset-sourced**
  figure, not invented — don't route it through the "illustrative"
  framing; say explicitly in your report and in a code comment that this
  one is real data, in 2004 USD (no inflation adjustment applied — note
  that as a limitation, don't silently invent an inflation factor).
- `financial_data`: **`capital_recovery_period=40`** — genuinely sourced
  from `scalars.csv`'s `trans_crp` row (confirmed by the controller:
  `trans_crp,40,--years-- transmission capital recovery period...`). The
  other 5 `TechnologyFinancialData` fields
  (`technology_base_year`/`debt_fraction`/`debt_rate`/`return_on_equity`/
  `tax_rate`) have no transmission-specific source in this dataset —
  illustrative, same honesty framing as elsewhere. Add a
  `transport_financial_data()`-style helper to `costs.py` that hardcodes
  `capital_recovery_period=40` with a comment naming `scalars.csv` as its
  source, distinct from the fully-illustrative `financial_data_for` used
  by E2/storage.
- `resistance`/`reactance`/`voltage`/`unit_size`: no dataset field backs
  these for this stage — leave at their schema defaults (`0.0`) rather
  than inventing values; note this in your report.

### `NodalHVDCTransportTechnology`

Data: `transmission/transmission_capacity_init_nonAC_nodal.csv` (1 row:
`b113,b316,LCC,100`) and
`transmission/transmission_distance_cost_500kVdc_nodal.csv` (1 row,
matching pair, `70` miles, `644267.96` USD2004perMW). One component:

- `start_node`/`end_node` from `b113`/`b316`.
- `capacity_limits = MinMax(min=0.0, max=100.0)`.
- `capital_costs` from the DC cost file's `USD2004perMW` (same
  sourced-not-invented note as AC).
- `financial_data`: same `capital_recovery_period=40` sourced value,
  same illustrative treatment for the rest.
- `line_loss: ValueCurve | None` — no dataset field backs this; leave
  `None`.

`add_transport_technologies(doc, source, inv_idx) -> tuple[dict, dict]`
(or whatever shape is natural; your call) covering both AC and HVDC.

## Verify

- Exactly 1 `StorageTechnology`, `power_systems_type ==
  "EnergyReservoirStorage"`, 1 `ExistingDevices` attribute with
  `existing_devices == ["313_STORAGE_1"]`.
- `duration_limits` is `None` on the `StorageTechnology`, with a test
  confirming both duration CSVs have zero data rows.
- `NodalACTransportTechnology` count == the number of unique
  `(From_Bus, To_Bus)` pairs in the capacity file (108, given the summing
  resolution above — assert against a fresh CSV read, not a hardcoded
  108).
- Every AC/HVDC `start_node`/`end_node` resolves to a real Node id (from
  E1's `node_id_by_bus_number`).
- 1 `NodalHVDCTransportTechnology`, `capacity_limits.max == 100.0`.
- Every transport `financial_data.capital_recovery_period == 40`.
- `doc.validate()` still passes.
- No `UserWarning`s under `-W error::UserWarning` from this stage's model
  construction (the `prime_mover_type` explicit-value note above is the
  known trap).

## Report

Write your full report to
`.claude/plans/task-E3-report.md`. Run
`cd python && uv run pytest tests/test_investments_storage.py
tests/test_investments_transport.py -v`, then `uv run pytest -m "not
slow"` for the full non-slow suite, then `uv run pytest -m "not slow" -W
error::UserWarning -q`. Reply with only DONE / DONE_WITH_CONCERNS /
NEEDS_CONTEXT / BLOCKED, the exact commands and pass counts, and a
one-line pointer to the report file.

State clearly in the report: the duplicate-AC-pair resolution you used
and the resulting transport-technology count (load-bearing for Task E6's
Julia cross-language check), which `StorageTechnology` capacity fields
you populated vs. left `None` and why, and the exact capital-cost figures
you picked for the battery.

If anything here is ambiguous in a way that's load-bearing for Task E6
(the combined-document build), ask before guessing rather than after.