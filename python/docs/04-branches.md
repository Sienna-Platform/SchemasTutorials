# 4. Branches

This stage reads two files, `SourceData/branch.csv` (AC) and `SourceData/dc_branch.csv` (the one
DC line), and produces `Arc`, `Line`, `TransformerCircuit`, `TwoWindingTransformer`, and
`TwoTerminalGenericHVDCLine`.

## The source

```
UID,From Bus,To Bus,R,X,B,Cont Rating,LTE Rating,STE Rating,Perm OutRate,Duration,Tr Ratio,Tran OutRate,Length
A1,101,102,0.003,0.014,0.461,175,193,200,0.24,16,0,0,3
A2,101,103,0.055,0.211,0.057,175,208,220,0.51,10,0,2.9,55
```
```
UID,From Bus,To Bus,Control Mode,R Line,MW Load,...,Margin,...
DC1,113,316,Power,5,100,500,5,0.1,Inverter,...
```

120 AC rows, 1 DC row. `Tr Ratio` is 0 for most rows, but not a clean 0/nonzero split — see below.

## The models

```python
from power_openapi_models.operations import models
[n for n in dir(models) if n in {
    "Arc", "Line", "TransformerCircuit", "TwoWindingTransformer",
    "TwoTerminalGenericHVDCLine",
}]
```
```
['Arc', 'Line', 'TransformerCircuit', 'TwoTerminalGenericHVDCLine', 'TwoWindingTransformer']
```

## Arcs: one per ordered (from, to) pair

`Arc` carries only `id`, `from_id`, `to_id` — no name, no electrical parameters, no units. Every
`Line`, `TransformerCircuit`, and the HVDC line all reference one; a bus pair seen more than once
(there are a few in `branch.csv`) reuses the same `Arc` rather than minting a duplicate. AC and DC
share the same cache: 108 distinct AC pairs + 1 DC pair = 109 arcs total.

## A line or a transformer?

The obvious rule — `Tr Ratio == 0` is a line, anything else is a transformer — gives 16
transformers. It's wrong for one row. Branch `C35` runs 230 kV → 230 kV with `Tr Ratio` exactly
`1.0`, `R = 0.0`, `B = 0.0`: an identity element between two buses at the *same* base voltage,
not a voltage-changing transformer. A tap of exactly 1.0 across equal base voltages does nothing
a transformer does — it's electrically a line that happens to carry a redundant tap field.

This build classifies branches by what a transformer actually is — a device that spans a voltage
change — and checks that rule against the naive one:

```python
is_transformer = from_kv != to_kv
tr_ratio_says_transformer = tr_ratio not in (0.0, 1.0)
if is_transformer != tr_ratio_says_transformer:
    raise ValueError(...)  # the two rules disagree — investigate before proceeding
```

Both formulations agree on every row except `C35`, where the voltage-based rule is correct: **105
lines, 15 transformers.** The correction is one word — `Tr Ratio not in (0.0, 1.0)` rather than
`Tr Ratio != 0.0` — but it changes which of 120 branches gets modeled as an identity transformer
versus a plain line.

## The mapping

Every branch component sets `power_units=NATURAL_UNITS` and an explicit `base_power=100.0`, same
as topology. Branches additionally set `parameter_units=COMPONENT_BASE` — the r/x/b values
RTS-GMLC provides are per-unit on a 100 MVA base, which is a different fact from what units the
*power* fields on this component are in. A natural-units case can and does carry per-unit
impedances; the two fields say so independently rather than one implying the other.

**`Line`** (source `A1`: R 0.003, X 0.014, B 0.461, ratings 175/193/200):

```python
Line(
    id=..., name="A1", available=True, arc=<arc id>,
    r=0.003, x=0.014,
    b={"from": 0.2305, "to": 0.2305},   # B/2 on each end
    g={"from": 0.0, "to": 0.0},
    rating=175.0, rating_b=193.0, rating_c=200.0,
    angle_limits={"min": -3.1416, "max": 3.1416},
    active_power_flow=0.0, reactive_power_flow=0.0,
    base_power=100.0, power_units="NATURAL_UNITS", parameter_units="COMPONENT_BASE",
)
```

**`TransformerCircuit`** carries the electrical parameters and has no `name` at all — the name
lives on the paired `TwoWindingTransformer`, which references the circuit by id:

```python
TransformerCircuit(
    id=..., available=True, arc=<arc id>,
    tap=1.015, alpha=0.0, r=0.002, x=0.084,
    control_objective="FIXED",
    control_limits={"min": 0.9, "max": 1.1},
    controlled_quantity_limits={"min": 1.0, "max": 1.0},
    regulated_bus_number=0, number_of_tap_positions=33,
    rating=400.0, rating_b=510.0, rating_c=600.0,
    active_power_flow=0.0, reactive_power_flow=0.0,
    base_power=100.0, power_units="NATURAL_UNITS", parameter_units="COMPONENT_BASE",
    base_voltage_primary=138.0, base_voltage_secondary=230.0,
)
TwoWindingTransformer(
    id=..., name="A7", circuit=<circuit id>,
    magnetizing_shunt={"real": 0.0, "imag": 0.0},
    shunt_location="PRIMARY", admittance_units="COMPONENT_BASE",
)
```

`loss` is a `LossCurve`, not a bare curve: the curve rides in its `value_curve` field, alongside
the curve's own `power_units`. Passing the bare curve does not fail — pydantic drops the unknown
keys and leaves the schema default, a zero-loss line — so this is one to get right by reading the
model rather than by watching for an error.

`number_of_tap_positions=33`, `regulated_bus_number=0`, and `controlled_quantity_limits`
`{1.0, 1.0}` aren't in RTS-GMLC's source data at all — they're conventions this build adopts for
every transformer, stated here rather than left unexplained in the code.

**`TwoTerminalGenericHVDCLine`** — the single `DC1` row, buses 113→316, `MW Load` 100, `Margin`
0.1:

```python
TwoTerminalGenericHVDCLine(
    id=..., name="DC1", available=True, arc=<fresh arc for 113->316>,
    active_power_flow=0.0,
    active_power_limits_from={"min": -100.0, "max": 100.0},   # ±MW Load
    active_power_limits_to={"min": -100.0, "max": 100.0},
    reactive_power_limits_from={"min": 0.0, "max": 100.0},
    reactive_power_limits_to={"min": 0.0, "max": 100.0},
    loss=LossCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve={"curve_type": "INPUT_OUTPUT", "function_data": {
            "function_type": "LINEAR", "constant_term": 0.0,
            "proportional_term": 0.1,   # Margin
        }},
    ),
    base_power=100.0, power_units="NATURAL_UNITS",
)
```

## Run it

```python
from rts_gmlc_case.branches import add_branches
add_branches(doc, src, idx)   # doc, src, idx from chapter 3
{k: len(v) for k, v in doc.document.components.items()
 if k in ("Arc", "Line", "TransformerCircuit", "TwoWindingTransformer", "TwoTerminalGenericHVDCLine")}
```
```
{'Arc': 109, 'Line': 105, 'TransformerCircuit': 15, 'TwoWindingTransformer': 15,
 'TwoTerminalGenericHVDCLine': 1}
```

## What to check

```sh
uv run pytest -q tests/test_branches.py
```
```
..                                                                       [100%]
2 passed in 0.47s
```

The main test derives the transformer count from a fresh `Tr Ratio`-based groupby *and*
independently from a voltage-based groupby, asserts they agree row for row, and checks every
count above plus arc dedup (109 unique pairs, no duplicates) and the HVDC line's exact field
values. The second test spot-checks line `A1`'s r/x/b/ratings/units against the source row shown
above.

Next: [05 — generators and costs](05-generation.md), the largest stage: 158 generators across six
component families.
