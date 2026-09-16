# 2. The document

Every stage in this tutorial adds components to one object: a `CaseDocument`. This chapter is
about what that object actually is, and the one thing worth knowing before touching a single row
of RTS-GMLC data: **the document has no global settings.**

## Finding it

```python
from power_openapi_models.document import SystemDocument
list(SystemDocument.model_fields)
```
```
['name', 'description', 'frequency', 'components',
 'supplemental_attributes', 'supplemental_attribute_associations',
 'plant_associations', 'combined_cycle_associations',
 'service_associations', 'trading_hub_associations',
 'time_series_associations', 'ext', 'time_series_storage_file']
```

That's the whole document. Look for a `base_power` or a `unit_system` field on it — there isn't
one. A first instinct when building a power system case is to set a document-wide base power and
a document-wide unit system once, at the top, and have every component inherit it implicitly.
This format rejects that instinct: `components` is just `dict[str, list[dict]]`, one bucket per
type name (`"ACBus"`, `"Line"`, `"ThermalStandard"`, …), and every component in every bucket
carries its own `base_power` and `power_units`. A reader of the JSON never has to look elsewhere
to know what units a value is in — nothing is inherited from a container. Chapter 3 onward, every
component this tutorial builds sets both fields explicitly.

The package ships the container (`SystemDocument`), plus `read_document`/`write_document` to
move it to and from a JSON file. What it does *not* ship is id minting, a convenience for
bucketing a component in, reference validation, or a way to get typed objects back out of those
untyped `dict` buckets. That's `rts_gmlc_case.document.CaseDocument` — a thin layer on top, not a
reimplementation.

## Ids are plain integers, minted in order

There is no UUID here. `CaseDocument.next_id()` hands out sequential integers starting at 1, and
every reference from one component to another — a bus number, an arc's two endpoints, a
generator's bus — is one of those integers. That's deliberate: an integer reference is
unambiguous, diffable, and trivial to validate (does this integer appear as an `id` somewhere in
`components`?). Ids are minted from one counter shared across every component type and every
association, so an `Area`, a `Line`, and a `TimeSeriesAssociation` never collide.

```python
from rts_gmlc_case.document import CaseDocument
from power_openapi_models.core.models import Area
from power_openapi_models.infrastructure_core.models import UnitSystem

doc = CaseDocument()
area_a = Area(id=doc.next_id(), name="1", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS)
area_b = Area(id=doc.next_id(), name="2", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS)
doc.add_component(area_a)
doc.add_component(area_b)
doc.document.components["Area"]
```
```
[{'id': 1, 'name': '1', 'peak_active_power': 0.0, 'peak_reactive_power': 0.0,
  'load_response': 0.0, 'base_power': 100.0, 'power_units': 'NATURAL_UNITS'},
 {'id': 2, 'name': '2', 'peak_active_power': 0.0, 'peak_reactive_power': 0.0,
  'load_response': 0.0, 'base_power': 100.0, 'power_units': 'NATURAL_UNITS'}]
```

`add_component` buckets by the model's own class name (`type(model).__name__`) and returns the
id, so a caller never hardcodes a bucket name — it falls out of which pydantic class you built.

## Validation is two checks

`doc.validate()` raises `ValueError` on the first problem it finds:

1. No two components share an id.
2. Every field in a known reference set (`bus`, `arc`, `area`, `load_zone`, `circuit`, `from_id`,
   `to_id`, `owner_id`, plus a few dynamics/converter fields) that is present and non-null points
   at an id that actually exists somewhere in `components`. Every `service_associations` row's
   `service_id`/`entity_id` is checked the same way.

```python
from power_openapi_models.core.models import Arc
doc.add_component(Arc(id=doc.next_id(), from_id=999, to_id=998))
doc.validate()
```
```
ValueError: unresolved reference: Arc id=3 field 'from_id' points to missing id 999
```

This is the only place in the whole build where a dangling reference gets caught before it
reaches the JSON file — every later chapter calls `doc.validate()` once, after every stage has
run.

## Typed re-parse

Writing a component runs it through `model_dump(mode="json", by_alias=True)` immediately, so
`components` holds plain dicts from the moment `add_component` returns. That's fine for writing,
but a consumer reading the case back wants real pydantic objects — enum members, not bare
strings; nested `MinMax`/`FromTo` objects, not nested dicts. `typed_components()` re-parses every
bucket through a registry built from the package's `core`, `operations`, `timeseries`, and
`infrastructure_core` modules, keyed by class name:

```python
typed = doc.typed_components()
typed["Area"][0]
```
```
Area(id=1, name='1', peak_active_power=0.0, peak_reactive_power=0.0,
     load_response=0.0, base_power=100.0, power_units=<UnitSystem.NATURAL_UNITS: 'NATURAL_UNITS'>)
```

Chapter 8's `read_case` is exactly `CaseDocument.read(path)` followed by `typed_components()` and
`validate()` — reading a case back is not a special path, it's the same validation the build
itself runs.

## What to check

```sh
uv run pytest -q tests/test_document.py
```
```
.....                                                                    [100%]
5 passed in 0.16s
```

Five tests: id minting and bucketing, a validation pass on resolvable references, the dangling-
reference and duplicate-id rejections shown above, and a full write/read/typed-reparse round trip
through a temp file.

Next: [03 — topology](03-topology.md), the first real stage — buses, areas, zones, and the three
bus shunts RTS-GMLC actually carries.
