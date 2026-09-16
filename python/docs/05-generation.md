# 5. Generators and costs

The largest stage: 158 rows in `SourceData/gen.csv`, dispatched across six component families by
a 12-entry lookup table, plus one row-pair join against `SourceData/storage.csv` for the single
storage unit.

## The source

```
GEN UID,Bus ID,Gen ID,Unit Group,Unit Type,Category,Fuel,MW Inj,MVAR Inj,V Setpoint p.u.,PMax MW,PMin MW,QMax MVAR,QMin MVAR,Min Down Time Hr,Min Up Time Hr,Ramp Rate MW/Min,...,Fuel Price $/MMBTU,Output_pct_0,Output_pct_1,Output_pct_2,Output_pct_3,Output_pct_4,HR_avg_0,HR_incr_1,HR_incr_2,HR_incr_3,HR_incr_4,VOM,...,Base MVA,...,Storage Roundtrip Efficiency
101_CT_1,101,1,U20,CT,Oil CT,Oil,8,4.96,1.0468,20,8,10,0,1,1,3,...,10.3494,0.4,0.6,0.8,1,NA,13114,9456,9476,10352,NA,0,...,24,...,0
```
```
GEN UID,Storage,Max Volume GWh,Initial Volume GWh,Start Energy,Inflow Limit GWh,Rating MVA,position
212_CSP_1,212_CSP_HEAD_STORAGE,1.2,0,0.04,0.1,200,head
313_STORAGE_1,313_HEAD_STORAGE,0.15,0.075,NA,0.1,50,head
```

## The models

```python
from power_openapi_models.operations import models
[n for n in dir(models) if n in {
    "ThermalStandard", "RenewableDispatch", "RenewableNonDispatch",
    "HydroDispatch", "SynchronousCondenser", "EnergyReservoirStorage",
}]
```
```
['EnergyReservoirStorage', 'HydroDispatch', 'RenewableDispatch',
 'RenewableNonDispatch', 'SynchronousCondenser', 'ThermalStandard']
```

## The mapping: 12 unit types, six targets

```python
UNIT_TYPE_TO_MODEL = {
    "NUCLEAR": "ThermalStandard", "STEAM": "ThermalStandard",
    "CT": "ThermalStandard",      "CC": "ThermalStandard",
    "WIND": "RenewableDispatch",  "PV": "RenewableDispatch", "CSP": "RenewableDispatch",
    "RTPV": "RenewableNonDispatch",
    "HYDRO": "HydroDispatch",     "ROR": "HydroDispatch",
    "SYNC_COND": "SynchronousCondenser",
    "STORAGE": "EnergyReservoirStorage",
}
```

`ROR` (run-of-river; one unit, `201_HYDRO_4`) is easy to miss — it reads as its own unit type
until you check the data and find exactly one row, which is hydro in every way that matters.
Twelve entries, not eleven; an unmapped `Unit Type` raises by name rather than silently falling
through.

Two fields are shared across every family and are unit conversions the raw CSV doesn't hint at:

- **`time_limits` is in minutes.** The source columns are `Min Up/Down Time Hr` — hours. Every
  `ThermalStandard` and `HydroDispatch` multiplies by 60 before setting `time_limits`. Miss this
  and every unit's minimum up/down time is understated 60×, silently — nothing fails, the case
  just quietly commits and decommits units 60 times faster than the source data says.
- **`rating` is family-specific, not one formula.** RTS-GMLC's fields don't map onto "rating"
  the same way for every technology:

  | Family | `rating` | Why |
  |---|---|---|
  | `ThermalStandard` | `hypot(PMax MW, QMax MVAR)` | apparent power from real+reactive limits |
  | `HydroDispatch` | `hypot(PMax MW, QMax MVAR)` | same formula, different number: `Base MVA` disagrees with it for hydro |
  | `RenewableDispatch`/`RenewableNonDispatch` | `Base MVA` | coincides with `PMax MW` in every one of 61 rows |
  | `SynchronousCondenser` | `QMax MVAR` | `Base MVA` is `0.0` in the source for all 3 rows — unusable |
  | `EnergyReservoirStorage` | `storage.csv`'s `Rating MVA` | no `gen.csv` field applies |

  `SynchronousCondenser` also has **no `prime_mover_type` field at all** in the model, and its
  `base_power` is a hardcoded `100.0` convention (not a CSV column) for the same reason its
  `Base MVA` is unusable: the source simply doesn't carry a synchronous condenser's base power.

## Thermal cost: a nested tree, not a flat curve

`101_CT_1`'s row: `PMax MW` 20.0, `Fuel Price $/MMBTU` 10.3494, `HR_avg_0` 13114.0, `HR_incr_1..3`
9456/9476/10352, `Output_pct_0..3` 0.4/0.6/0.8/1.0 (`Output_pct_4` is blank), `Start Heat Cold
MBTU` 5.0, `Non Fuel Start Cost $` 0, `VOM` 0.0. `operation_cost` on a `ThermalStandard` is four
levels deep:

```
operation_cost                                 (ThermalGenerationCost, cost_type=THERMAL)
└─ variable_operation_cost                     (a FuelCurve)
   ├─ value_curve                              (curve_type=INCREMENTAL)
   │  └─ function_data                         (function_type=PIECEWISE_STEP)
   │     ├─ x_coords: Output_pct_k × PMax MW, nonempty blocks only
   │     └─ y_coords: HR_incr_k for k ≥ 1
   └─ vom_cost                                 (curve_type=INPUT_OUTPUT, function_type=LINEAR)
```

`curve_type` (`INCREMENTAL`) and `function_type` (`PIECEWISE_STEP`) are two independent
discriminators on two different nesting levels — easy to conflate, worth naming separately. The
formulas, verified against `101_CT_1`:

| Quantity | Formula | `101_CT_1` value |
|---|---|---|
| `x_coords` | `Output_pct_k × PMax MW`, nonempty blocks | `[8.0, 12.0, 16.0, 20.0]` |
| `y_coords` | `HR_incr_k`, `k ≥ 1` | `[9456.0, 9476.0, 10352.0]` |
| `initial_input` | `HR_avg_0 × x_coords[0]` — no ×1000 factor | `104912.0` |
| `fuel_cost` | `Fuel Price $/MMBTU ÷ 1000` | `0.0103494` |
| `start_up` | `Non Fuel Start Cost $ + Start Heat Cold MBTU × Fuel Price` | `51.747` |
| `shut_down` | `Non Fuel Shutdown Cost $` | `0.0` |

The built case's actual `101_CT_1`:

```json
{
  "name": "101_CT_1", "status": "ONLINE", "commitment_mode": "MARKET",
  "rating": 22.360679774997898,
  "active_power_limits": {"max": 20.0, "min": 8.0},
  "ramp_limits": {"down": 3.0, "up": 3.0},
  "operation_cost": {
    "cost_type": "THERMAL", "fixed": 0.0, "shut_down": 0.0, "start_up": 51.747,
    "variable_operation_cost": {
      "fuel_cost": 0.0103494, "variable_cost_type": "FUEL",
      "value_curve": {
        "curve_type": "INCREMENTAL",
        "function_data": {"function_type": "PIECEWISE_STEP",
                           "x_coords": [8.0, 12.0, 16.0, 20.0],
                           "y_coords": [9456.0, 9476.0, 10352.0]},
        "initial_input": 104912.0
      },
      "vom_cost": {"curve_type": "INPUT_OUTPUT",
                   "function_data": {"function_type": "LINEAR",
                                     "constant_term": 0.0, "proportional_term": 0.0}}
    }
  },
  "base_power": 24.0, "time_limits": {"down": 60.0, "up": 60.0},
  "commitment_mode": "COMMITTED", "prime_mover_type": "CT", "fuel": "DISTILLATE_FUEL_OIL",
  "time_at_status": 600000.0
}
```

Three fields worth flagging by name, present on every thermal unit and easy to miss reading the
source alone: `time_at_status: 600000.0` and `commitment_mode: "COMMITTED"` are fixed conventions
(RTS-GMLC carries neither), and `status = "ONLINE"` is a deliberate choice, covered next.
`commitment_mode` replaced an earlier boolean `must_run`; `COMMITTED` is the field's own default
and the closest analogue for an online, dispatchable thermal unit.

## `status`: RTS-GMLC has no initial commitment state

`ThermalStandard.status` is a *required* enum (`OFFLINE`/`STARTUP`/`ONLINE`/`SHUTDOWN`). RTS-GMLC
doesn't carry an initial on/off state for any unit — there's no column for it. Every thermal unit
in this build sets `status = OperationalStates.ONLINE`. That's the tutorial's own convention for
"what does the case look like at the first instant," not a fact recovered from the source data,
and it's worth knowing before scheduling anything against this case: every unit starts committed.

## Storage: one row picked from a pair, and a real efficiency figure

`storage.csv` isn't one row per generator. `313_STORAGE_1` (the only `STORAGE`-typed generator)
has two rows — `position` `head` and `tail`, describing the same physical reservoir from two
ends. This build reads the `head` row for determinism (both rows carry identical values for
every field actually used here, so nothing is lost by the choice — but a `groupby` that assumes
one row per `GEN UID` would silently double-count).

`storage.csv` also carries a real `Storage Roundtrip Efficiency` — 85% for `313_STORAGE_1` — that
this build actually uses. Round-trip efficiency splits across the charge and discharge legs as
`sqrt(0.85)` each:

```python
leg_efficiency = math.sqrt(0.85)   # 0.9219544457292888, each leg
```

```json
{
  "name": "313_STORAGE_1", "storage_capacity": 150.0, "rating": 50.0,
  "initial_storage_capacity_level": 0.5,
  "efficiency": {"in": 0.9219544457292888, "out": 0.9219544457292888},
  "input_active_power_limits": {"max": 100.0, "min": 0.0},
  "output_active_power_limits": {"max": 50.0, "min": 0.0}
}
```

`input_active_power_limits.max` is `2 × Pump Load MW` — the charging capacity the source
actually states, chosen over the alternative `2 × Base MVA` (both give 100.0 here, so the two
can't be told apart from this one row, but `Pump Load MW` is the more literal source for "how
fast can this unit charge").

## What to check

```sh
uv run pytest -q tests/test_generation.py
```
```
.....                                                                    [100%]
5 passed in 0.56s
```

Five tests: every `Unit Type` in `gen.csv` covered by the 12-entry table, per-target counts
matching a fresh `groupby` (73 `ThermalStandard`, 30 `RenewableDispatch`, 31
`RenewableNonDispatch`, 20 `HydroDispatch`, 3 `SynchronousCondenser`, 1
`EnergyReservoirStorage`); `101_CT_1`'s full cost tree against the table above; the
family-specific rating rules (including the `SynchronousCondenser`'s missing
`prime_mover_type` field and hardcoded `base_power`); the storage efficiency figure; and that an
unmapped `Unit Type` or `Fuel` raises naming the offending row.

Next: [06 — loads, storage, reserves](06-demand.md), the demand side: 51 loads and 7 reserve
products joined against 510 eligible generators.
