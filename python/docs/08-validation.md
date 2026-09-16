# 8. Validation and reading the case back

`rts_gmlc_case.build` composes every earlier chapter into one fixed pipeline and adds the checks
that make the result trustworthy: every reference resolves, every id is unique, the same source
data produces byte-identical output every time, and the finished case reads back through the same
typed layer it was built with.

```python
from rts_gmlc_case.build import build_case
```
```python
def build_case(case_dir):
    doc = CaseDocument()
    idx = add_topology(doc, source)
    add_branches(doc, source, idx)
    gen_ids = add_generation(doc, source, idx)
    add_loads(doc, source, idx)
    reserve_ids = add_reserves(doc, source, idx, gen_ids)
    attach_time_series(doc, source, sidecar, owners)
    doc.validate()
    doc.write(case_dir / "system.json")
    return doc
```

The stage order — topology → branches → generation → loads → reserves → time series — is load-
bearing, not incidental. Every later stage's components reference ids an earlier stage minted (an
`Arc`'s buses, a generator's bus, a reserve's eligible generators, a time-series association's
owner), so this fixed order is what makes a given source dataset mint the same id sequence on
every run — the id-determinism check below depends on it.

## Ids: one counter, two ranges

Every component and every time-series association draws from the same counter chapter 2
introduced (`CaseDocument.next_id()`). The finished case has 561 components and 282 time-series
associations, and the ranges don't overlap because nothing resets the counter between them:

```python
component_ids = [item["id"] for items in doc["components"].values() for item in items]
assoc_ids = [a["association_id"] for a in doc["time_series_associations"]]
min(component_ids), max(component_ids), len(component_ids)
min(assoc_ids), max(assoc_ids), len(assoc_ids)
```
```
(1, 561, 561)
(562, 843, 282)
```

Components occupy 1–561; associations occupy 562–843, picking up exactly where components left
off. `service_associations` mints no ids of its own — each row is just two existing component
ids (chapter 6).

## The 146-vs-282 dedup result

The parquet sidecar (chapter 7) is content-addressed, so the number of distinct files is a real
measurement of how much of the 282-association time-series data is actually distinct:

```sh
ls timeseries/*.parquet | wc -l
```
```
146
```

282 associations, 146 files: every `PMax`/`PMin` pair sharing a source column (102 of them) and
every object sharing a data file with another collapse onto one file. This isn't a target anyone
picked — it falls out of hashing real content, and it's a strong signal the sidecar's dedup logic
(chapter 7) is doing its job rather than silently writing 282 near-duplicate files.

## `read_case`: the same typed layer, run in reverse

```python
def read_case(case_dir):
    doc = CaseDocument.read(case_dir / "system.json")
    doc.typed_components()
    doc.validate()
    return doc
```

Reading a case back isn't a separate code path from building one — it's `CaseDocument.read`
(chapter 2's `read_document`, plus restoring the id counter to one past the largest id seen),
then the same `typed_components()` re-parse and the same `validate()` every stage already calls.
A bad alias or an enum-coercion bug in either direction surfaces here, not downstream in whatever
reads the case next:

```python
from rts_gmlc_case.build import read_case
doc = read_case(case_dir)
typed = doc.typed_components()
sorted(typed.keys())
type(typed["ACBus"][0])
typed["ACBus"][0].name, typed["ACBus"][0].number
doc.next_id()
```
```
['ACBus', 'Arc', 'Area', 'EnergyReservoirStorage', 'FixedAdmittance', 'HydroDispatch', 'Line',
 'LoadZone', 'OnlineReserve', 'PowerLoad', 'RenewableDispatch', 'RenewableNonDispatch',
 'SynchronousCondenser', 'ThermalStandard', 'TransformerCircuit', 'TwoTerminalGenericHVDCLine',
 'TwoWindingTransformer']
<class 'power_openapi_models.operations.models.ACBus'>
('Abel', 101)
562
```

`next_id()` returning `562` after a read (not `1`) is the counter-restoration working correctly —
appending anything new to a case read back from disk continues the same id sequence rather than
colliding with what's already there.

## What `build_case` checks before it writes anything

`doc.validate()` runs once, after every stage — the same two checks chapter 2 introduced, now
covering the whole document: no duplicate id across any of the 17 component types, and every
reference field (a bus, an arc, a load zone, a circuit, a service association's two ids) resolves.
Nothing gets written to `system.json` if either check fails.

## Determinism

Running `build_case` twice against the same cached source data produces byte-identical
`system.json` files. That's a real, checked property — the build's driver test builds the case
twice into separate directories and compares the raw bytes, not just the parsed structure. It
depends on every stage doing the same thing this tutorial has stressed throughout: areas and
zones added in sorted order (chapter 3), arcs deduplicated by ordered pair (chapter 4), a fixed
stage order (this chapter) — anywhere a Python `dict` or `set` iteration order could leak into
output, this build avoids depending on it.

## What to check

The full pipeline builds and reads back the pinned RTS-GMLC dataset already cached from chapter
1. **Building it yourself is the one command in this tutorial with a real cost** — 282
time-series profiles, several at 100k+ rows — so if you already have a built case (this
tutorial's own reference build lives at the repo's `cases/rts-python/`), read from it instead of
rebuilding:

```sh
uv run python build_rts.py <output-dir>
```
```
wrote case to <output-dir>
component counts:
  ACBus: 73
  Arc: 109
  Area: 3
  EnergyReservoirStorage: 1
  FixedAdmittance: 3
  HydroDispatch: 20
  Line: 105
  LoadZone: 21
  OnlineReserve: 7
  PowerLoad: 51
  RenewableDispatch: 30
  RenewableNonDispatch: 31
  SynchronousCondenser: 3
  ThermalStandard: 73
  TransformerCircuit: 15
  TwoTerminalGenericHVDCLine: 1
  TwoWindingTransformer: 15
service_associations: 510
time_series_associations: 282
parquet files: 146
```

The full suite, including the five build-and-read tests marked `slow` (each performs one
complete build), runs as:

```sh
uv run pytest -q
```

and without them, for everything short of the actual end-to-end build:

```sh
uv run pytest -q -m "not slow"
```

The `slow` tests check exactly what this chapter describes: the component-count table above; id
uniqueness across the whole 561-component document; a bucket-by-bucket match between a freshly
built case's typed components and the same case read back (`read_case`); that every time-series
association's parquet file exists with the right row count and that the on-disk file set has no
orphans, with the dedup count strictly below 282; and the two-independent-builds byte-identity
check.

## Where this leaves a reader

Seven CSV tables in, one JSON document and a folder of parquet files out: 73 buses across 3 areas
and 21 zones, 3 bus shunts, 109 arcs carrying 105 lines and 15 transformer circuits and one HVDC
line, 158 generators across six component families, 51 loads, 7 reserve products backing 510
generator eligibility associations, and 282 time-series pointers collapsed into 146 distinct
value files. Every id is a plain integer, every unit is explicit on the component that carries it,
and nothing about the result depends on how it was produced — that's what "portable" means here.

Back to [the README](../README.md) for the full chapter list.
