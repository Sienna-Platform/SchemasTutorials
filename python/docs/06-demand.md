# 6. Loads, storage, reserves

This stage reads `bus.csv` again (this time for load, not topology), plus `reserves.csv`, and
produces `PowerLoad`, `OnlineReserve`, and `service_associations` — the rows linking each reserve
to the generators eligible to provide it.

## The source

```
Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,...
101,Abel,138.0,PV,108.0,22.0,...
```
```
Reserve Product,Timeframe (sec),Requirement (MW),Eligible Regions,Eligible Device Categories,Eligible Device SubCategories,Direction
Spin_Up_R1,600,40.413,1,(Generator),"(Gas CT,Gas CC,Oil CT,Oil ST,Coal,Solar PV,Wind,CSP)",Up
Flex_Up,1200,96.000,"(1,2,3)",(Generator),"(Gas CT,Gas CC,Oil CT,Oil ST,Coal,Solar PV,Wind,CSP)",Up
```

7 reserve products. 51 of 73 buses have nonzero `MW Load`.

## The models

```python
from power_openapi_models.operations import models
[n for n in dir(models) if n in {"PowerLoad", "OnlineReserve", "ServiceAssociation"}]
```
```
['OnlineReserve', 'PowerLoad', 'ServiceAssociation']
```

`VariableReserve` is not in that list — it doesn't exist. RTS-GMLC's reserve products (spinning
and regulation reserves) map onto `OnlineReserve`, which the package does provide alongside
`OfflineReserve` and `GroupReserve`.

## `PowerLoad`: one per bus with load

```python
PowerLoad(
    id=..., name="Abel", available=True, bus=<Abel's ACBus id>,
    active_power=108.0, max_active_power=108.0,
    reactive_power=22.0, max_reactive_power=22.0,
    base_power=100.0, power_units="NATURAL_UNITS",
    conformity="UNDEFINED",
)
```

Both the instantaneous and the max fields are set to the same source value at build time —
chapter 7 attaches an hourly profile that scales `max_active_power` over the year.
`conformity="UNDEFINED"` isn't in the source data at all; it's a required field with no RTS-GMLC
equivalent, so every load gets the same explicit placeholder rather than an implicit default.

## `OnlineReserve`: both time fields are in minutes

```python
OnlineReserve(
    id=..., name="Spin_Up_R1", available=True,
    time_frame=10.0,          # Timeframe (sec) / 60  — 600 sec -> 10.0 min
    requirement=40.413,       # Requirement (MW), straight through
    sustained_time=60.0,      # one hour, in minutes — fixed for every product
    max_output_fraction=1.0, max_participation_factor=1.0, deployed_fraction=0.0,
    reserve_direction="UP",   # Direction: Up -> UP, Down -> DOWN
)
```

`Timeframe (sec)` reads as seconds and the field is named `time_frame`, so it's tempting to copy
it straight across. Both this build's time fields are minutes: `time_frame` divides the source
seconds by 60 (600 → 10.0, 1200 → 20.0, 300 → 5.0), and `sustained_time` is a fixed 60.0 for every
product — one hour, expressed the same way as `time_frame`. Getting this wrong doesn't error; it
produces a plausible-looking case whose response windows are 60× too long and whose sustained
time is 60× too short.

## Eligibility: the source states its own vocabulary — use it directly

A reserve's `Eligible Device SubCategories` field is a parenthesized list:
`(Gas CT,Gas CC,Oil CT,Oil ST,Coal,Solar PV,Wind,CSP)`. `gen.csv` has its own `Category` column,
and its values are **exactly** that vocabulary:

```python
import pandas as pd
gen = pd.read_csv(src / "gen.csv")
gen["Category"].value_counts()
```
```
Solar RTPV    31
Gas CT        27
Solar PV      25
Hydro         20
Coal          16
Oil CT        12
Gas CC        10
Oil ST         7
Wind           4
Sync_Cond      3
Nuclear        1
CSP            1
Storage        1
```

Eligibility is a direct join — parse `Eligible Device SubCategories` into a set, keep generators
whose own `Category` is in it — with no hardcoded (Unit Type, Fuel) table standing between them.
The region filter works the same way against `Eligible Regions`, matched to each generator's bus
`Area`. Both fields come in two shapes: a bare value (`"1"`) or a parenthesized comma list
(`"(1,2,3)"`); one small parser handles both.

```json
{"service_id": 555, "entity_id": 346}
```

That's the whole record — `service_id` is `Spin_Up_R1`'s `OnlineReserve` id, `entity_id` is
`101_CT_1`'s `ThermalStandard` id. **510 rows total**, and the per-product counts
are a strong end-to-end check that both filters are right:

| Product | Region | Associations |
|---|---|---|
| Spin_Up_R1 | 1 | 34 |
| Spin_Up_R2 | 2 | 25 |
| Spin_Up_R3 | 3 | 43 |
| Flex_Up | 1,2,3 | 102 |
| Flex_Down | 1,2,3 | 102 |
| Reg_Up | 1,2,3 | 102 |
| Reg_Down | 1,2,3 | 102 |

34 + 25 + 43 = 102 (the region-scoped spinning products partition the same 102 category-eligible
generators three ways), and 102 + 4×102 = **510**.

## What to check

```sh
uv run pytest -q tests/test_demand.py
```
```
....                                                                     [100%]
4 passed in 0.62s
```

Four tests: the 51-load count and bus 101 (Abel)'s exact field values against the mapping above;
all seven reserves' minute-converted `time_frame`/`sustained_time` and direction; and the
per-product association counts in the table above, totaling 510.

Next: [07 — time series and the parquet sidecar](07-timeseries.md) — the sidecar contract that
turns 282 pointer rows into a portable, content-addressed folder of value files.
