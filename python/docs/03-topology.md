# 3. Topology

Every later stage needs buses to attach things to. This stage reads one file,
`SourceData/bus.csv`, and produces four component types: `Area`, `LoadZone`, `ACBus`, and —
for three buses only — `FixedAdmittance`.

## The source

```
Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,V Mag,V Angle,MW Shunt G,MVAR Shunt B,Area,Sub Area,Zone,lat,lng
101,Abel,138.0,PV,108.0,22.0,1.04777,-7.74152,0.0,0.0,1,11.0,11.0,33.3961032628,-113.835641977
102,Adams,138.0,PV,97.0,20.0,1.04783,-7.81784,0.0,0.0,1,11.0,12.0,33.3576784424,-113.825933492
```

73 rows. `Area` and `Zone` are small integers; `Bus Type` is `PQ`, `PV`, or `Ref`.

## The models

```python
from power_openapi_models.operations import models
[n for n in dir(models) if n in {"ACBus", "Area", "LoadZone", "FixedAdmittance"}]
```
```
['ACBus', 'Area', 'FixedAdmittance', 'LoadZone']
```
```python
from power_openapi_models.core.models import ACBusType
list(ACBusType)
```
```
[<ACBusType.PQ: 'PQ'>, <ACBusType.PV: 'PV'>, <ACBusType.REF: 'REF'>,
 <ACBusType.ISOLATED: 'ISOLATED'>, <ACBusType.SLACK: 'SLACK'>]
```

`ACBusType` has no `Ref` member — the enum spells it `REF`. `rts_gmlc_case.topology._normalize_bustype`
does the one normalization RTS-GMLC's spelling needs: `"Ref"` → `ACBusType.REF`, everything else
just uppercased.

## The mapping

| Source | Target | Notes |
|---|---|---|
| one row per distinct `Area` value | `Area` | 3 areas; `peak_active_power`/`peak_reactive_power` are the per-area sum of `MW Load`/`MVAR Load` |
| one row per distinct `Zone` value | `LoadZone` | **21 zones, not 3** — see below |
| every `bus.csv` row | `ACBus` | `number`=`Bus ID`, `bustype` from `Bus Type`, `angle`=`radians(V Angle)`, `magnitude`=`V Mag`, `base_voltage`=`BaseKV` |
| `MW Shunt G`/`MVAR Shunt B` nonzero | `FixedAdmittance` | 3 buses only — see below |

Both `Area` and `LoadZone` set `base_power=100.0` and `power_units=UnitSystem.NATURAL_UNITS`
explicitly (chapter 2: there's no document-level unit system to inherit). `ACBus` carries a fixed
`voltage_limits = {min: 0.95, max: 1.05}` for every bus — RTS-GMLC's source data doesn't carry
per-bus voltage limits, so this is a tutorial convention, not a source value.

Areas and zones are added in sorted numeric order specifically so their minted ids are
deterministic across independent runs — build the case twice and every id lands the same place.

### Why 21 zones, not 3

RTS-GMLC's `Zone` column has 21 distinct values (11–17, 21–27, 31–37), nested three-to-a-digit
under 3 areas. Collapsing straight to one `LoadZone` per `Area` would throw that nesting away.
This build keeps it: one `LoadZone` per distinct `Zone` value, so the finer-grained zone
structure survives into the case document even though it costs 21 components instead of 3.

### Three buses carry a shunt

Two source columns, `MW Shunt G` and `MVAR Shunt B`, are zero for every bus except three:
106 (Alber), 206 (Bajer), 306 (Camus), each with `MVAR Shunt B = -100.0` and `MW Shunt G = 0.0`.
Silently dropping three real shunts because they're rare would mismodel each bus's reactive
compensation, so each nonzero row gets one `FixedAdmittance`:

```python
from power_openapi_models.core.models import ShuntAdmittanceUnitBasis
from power_openapi_models.infrastructure_core.models import ComplexNumber
from power_openapi_models.operations.models import FixedAdmittance

FixedAdmittance(
    id=..., name="Alber_shunt", available=True, bus=<Alber's ACBus id>,
    Y=ComplexNumber(real=0.0, imag=-100.0),
    base_power=100.0,
    admittance_units=ShuntAdmittanceUnitBasis.NATURAL_UNITS,
)
```

`ShuntAdmittanceUnitBasis` has two members, `NATURAL_UNITS` and `COMPONENT_MVAR`; the field's
plain default is the bare string `"COMPONENT_MVAR"` rather than the enum member, which trips a
pydantic serializer warning if left unset. Setting it explicitly avoids that and matches every
other component's explicit `power_units`.

## Run it

```python
from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import add_topology

src = data.rts_source_dir() / "SourceData"
doc = CaseDocument()
idx = add_topology(doc, src)
{k: len(v) for k, v in doc.document.components.items()}
```
```
{'Area': 3, 'LoadZone': 21, 'ACBus': 73, 'FixedAdmittance': 3}
```

`add_topology` returns a `TopologyIndex` — `bus_id_by_number`, `area_id_by_name`,
`zone_id_by_name` — the lookup table every later stage uses to turn a source-data bus number
into a minted component id.

## What to check

```sh
uv run pytest -q tests/test_topology.py
```
```
.                                                                        [100%]
1 passed in 0.47s
```

One test, several assertions: the four counts above (73/3/21/3), bus 101's name and angle
converted correctly, all three shunt names and their `Y` values, that both classification rules
for area/zone membership agree with a fresh `groupby` over the CSV (not a copy of the expected
numbers), that per-area and per-zone load sums add up to the same system total, and that
`doc.validate()` passes with nothing else in the document yet.

Next: [04 — branches](04-branches.md), which needs `TopologyIndex.bus_id_by_number` to connect
lines and transformers to real buses.
