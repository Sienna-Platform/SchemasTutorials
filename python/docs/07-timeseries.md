# 7. Time series and the parquet sidecar

282 rows in `SourceData/timeseries_pointers.csv` each name one profile — a generator's dispatch
limit, an area's load, a reserve's requirement — and where to find its data. This stage reads
every one, writes its values through a content-addressed parquet store, and attaches a
`TimeSeriesAssociation` to the document. This chapter states that store's contract in full: it's
the one piece of this format meant to be reimplemented by another language, not just read.

## The source

```
Simulation,Category,Object,Parameter,Scaling Factor,Data File
DAY_AHEAD,Generator,122_HYDRO_1,PMax MW,52.49761899,../timeseries_data_files/HYDRO/DAY_AHEAD_hydro.csv
DAY_AHEAD,Generator,122_HYDRO_2,PMax MW,52.49761899,../timeseries_data_files/HYDRO/DAY_AHEAD_hydro.csv
```

`Category` is one of `Generator`, `Area`/`Region`/`Zone`, or `Reserve`; `Parameter` names what
the profile scales. `Data File` is a relative path into `timeseries_data_files/`.

## The sidecar contract

Every value vector this build writes goes through the same store, laid out beside the JSON
document:

- **Location:** a `timeseries/` folder next to `system.json`.
- **One file per distinct series**, named `ts_<first 16 hex chars of data_hash>.parquet`.
- **Two columns:** `timestamp` as `pa.timestamp("ms", tz="UTC")` (always UTC — a tz-naive input
  is rejected outright, never silently assumed to be UTC; a tz-aware non-UTC input is converted),
  and `value` as float64.
- **`data_hash`** is a SHA-256 hex digest over the value vector's bytes, encoded as float64
  **little-endian** (`<f8`) rather than the platform-native byte order — native order depends on
  the machine, so pinning little-endian is what makes the digest reproducible across machines and
  across a language boundary. An all-integer input is cast to float64 *before* hashing, so it
  matches whatever another implementation's native float type hashes to for the same logical
  values.
- **The hash covers `values` only, never `timestamps`.** The timestamp column's dtype and UTC-ms
  convention are enforced by the writer, but they aren't part of the digest and aren't otherwise
  verified — the hash is a content address for the value vector, not the whole file.
- **NaN payload bits and the sign of zero are hashed as raw bytes, not canonicalized.** Two NaNs
  that differ only in mantissa payload hash differently, and `0.0`/`-0.0` — which compare equal
  under `==` — hash differently too. This is deliberate: a byte-identical hash is the entire point
  of a cross-language content address, and silently normalizing either would hide a real
  bit-level difference between two producers of the same nominal values.
- **Content dedup:** writing the same value vector twice yields one file and the same `uri`. The
  write itself is atomic (write to a temp file, then rename into place) so a path is always
  either absent or a complete, valid file — never partially written.

Pinned cross-language literal, checked in a test on both language implementations of this
contract:

```python
from rts_gmlc_case.sidecar import data_hash
import numpy as np
data_hash(np.array([1.0, 2.0, 3.0]))
```
```
'a68de4b5e96a60c8ceb3c7b7ef93461725bdbbff3516b136585a743b5c0ec664'
```

## Two CSV layouts, one output shape

RTS-GMLC's own time-series files aren't uniform. Every generator directory (`WIND`, `PV`, `RTPV`,
`Hydro`, `CSP`) and `Load/` use **Layout A** — one row per period, one column per object:

```
Year,Month,Day,Period,122_HYDRO_1,122_HYDRO_2,...
2020,1,1,1,142.8,795.1,...
```

`Period` resets every day (1..24 for `DAY_AHEAD`, 1..288 for `REAL_TIME`), so the timestamp is
`day + (Period-1) × resolution`, not a running index — and the pointer's `Object` selects a
column.

`Reserves/` mixes two layouts in the same directory: `Spin_Up_R1`/`R2`/`R3` are Layout A like
everything else, but `Flex_Up`/`Flex_Down`/`Reg_Up`/`Reg_Down` are **Layout B** — periods as
columns, one row per day, no `Period` column and no per-object column at all:

```
Year,Month,Day,1,2,3,...,24
2020,1,1,142.8,140.2,138.9,...
```

The whole file is one series here; the pointer's `Object` (the product name) selects the *file*,
and there's nothing left to select a column with. `read_profile` doesn't classify by which
directory a file lives in — it detects the layout by whether a `Period` column is present, which
turns out to be the only rule that survives being checked against all 12 files in `Reserves/`
(6 Layout A, 6 Layout B — not, as it might look from the outside, "all of `Reserves/` is one
layout"). Layout B is flattened row-major — day by day, period ascending within each day — to the
same `(timestamps, values)` shape Layout A produces, so every caller downstream sees one uniform
shape regardless of source layout.

## Owner resolution and the target field

`Parameter` maps to two things: the association's `name` (the field it fills, not
`component_field`, which stays unset) and a `quantity_kind`:

| `Parameter` | `name` | `quantity_kind` |
|---|---|---|
| `PMax MW` | `max_active_power` | `active_power` |
| `PMin MW` | `min_active_power` | `active_power` |
| `MW Load` | `max_active_power` | `active_power` |
| `Requirement` | `requirement` | `active_power` |
| `Natural_Inflow` | `inflow` | `power` |

`Category == "Generator"` resolves `Object` against the generator id map by `GEN UID` — except
the two `Natural_Inflow` rows, whose `Object` is `212_CSP_HEAD_STORAGE`, a name from
`storage.csv`'s `Storage` column, not a `GEN UID`. Those resolve through `storage.csv`'s
`Storage → GEN UID` join to `212_CSP_1` instead; this build doesn't model storage vessels as
separate components, so the inflow series attaches to the generator that owns the reservoir.
`Category` in `("Area", "Region", "Zone")` resolves to an `Area` by name; `Category == "Reserve"`
resolves to the matching `OnlineReserve`.

## Paths don't match their own casing

Walking every one of RTS-GMLC's 24 distinct `Data File` values against the real directory listing
turns up two mismatches: the `HYDRO` directory referenced in the pointers is `Hydro` on disk (80
of 282 pointers), and `Load/REAL_TIME_regional_load.csv` is really
`REAL_TIME_regional_Load.csv`. That's **83 of 282 pointer rows — 29%** — referencing a path that
doesn't exist under exact-case matching. It resolves silently on a case-insensitive filesystem and
raises `FileNotFoundError` everywhere else, which makes it a landmine for anyone who runs this
build on Linux rather than the machine it was written on: a build that works for its author and
fails for everyone else with no clue why.

`resolve_case_insensitive_path` walks the path one component at a time, matching exactly first
and falling back to a case-insensitive match — and raises, naming the path, on zero or on more
than one match, so an ambiguous or genuinely-missing entry never resolves silently either.
`Path.exists()` can't be used to check this, because it's *itself* case-insensitive on the same
filesystems that hide the bug — walking `iterdir()` and comparing names explicitly is what
catches both the directory case (`HYDRO`/`Hydro`) and the filename case
(`REAL_TIME_regional_load.csv`/`REAL_TIME_regional_Load.csv`); checking directories alone misses
the second.

## `TimeSeriesAssociation`: the full record

```json
{
  "association_id": 562,
  "owner_id": 420, "owner_type": "HydroDispatch", "owner_category": "Component",
  "time_series_type": "SingleTimeSeries",
  "name": "max_active_power",
  "features": {},
  "uri": "timeseries/ts_d74e65b58d43f02c.parquet",
  "data_hash": "d74e65b58d43f02cc9b38200038a7322a102a8dc9785bd17eff38b5a4e26ab56",
  "element_type": "f64", "element_shape": [], "array_shape": [8784],
  "units": "MW", "quantity_kind": "active_power",
  "unit_system": "NATURAL_UNITS", "time_reference": "zoneless",
  "initial_timestamp": "2020-01-01T00:00:00Z",
  "resolution": "PT1H", "length": 8784
}
```

`resolution` is `PT1H` for `DAY_AHEAD` and `PT5M` for `REAL_TIME`. `element_type` is always the
literal `"f64"` — it isn't an enforced enum in this package (any string validates), so both this
build and any consumer reading it back agree on the one literal by convention rather than by type
system. `time_reference: "zoneless"` appears on every record regardless — the timestamps
themselves are UTC-aware; this field describes something else about the series. `unit_system:
"NATURAL_UNITS"` means what chapter 2 says it always means: the value in this parquet file, after
the pointer's `Scaling Factor` has already been applied, is in the same physical units
(megawatts) as the component field it fills — not a per-unit profile a reader has to rescale
against something else.

## The 122_HYDRO_1 dedup check

102 of 282 pointer rows are `PMin MW` — and for every one of those 51 objects, `PMax MW` and
`PMin MW` point at the *same* `Data File` with the *same* `Scaling Factor`. Byte-identical
inputs hash identically, so the sidecar collapses each such pair onto one file:

```python
gen_id = <122_HYDRO_1's id>
[(a["name"], a["uri"].split("/")[-1]) for a in doc["time_series_associations"] if a["owner_id"] == gen_id]
```
```
[('max_active_power', 'ts_d74e65b58d43f02c.parquet'),
 ('min_active_power', 'ts_d74e65b58d43f02c.parquet'),
 ('max_active_power', 'ts_257c12fa91101955.parquet'),
 ('min_active_power', 'ts_257c12fa91101955.parquet')]
```
(the first pair is `DAY_AHEAD`, the second `REAL_TIME` — same dedup holds at both resolutions).
This is the single strongest end-to-end check of the whole content-addressed design: 282
associations, but **146 distinct parquet files** — every hydro/ROR/RTPV `PMax`/`PMin` pair and
every object that shares a source column with another collapses onto one file.

## What to check

```sh
uv run pytest -q tests/test_sidecar.py
```
```
.............                                                            [100%]
13 passed in 0.41s
```
```sh
uv run pytest -q tests/test_timeseries.py
```
```
..............                                                           [100%]
14 passed in 11.88s
```

`test_sidecar.py` covers the hash pin above, dedup on identical writes, distinct files
for distinct values, the tz-naive rejection and tz-aware conversion, atomic-write cleanup on
failure, and the raw-bytes NaN/signed-zero behavior. `test_timeseries.py` (14 tests) covers both
CSV layouts (including a deliberately constructed case-mismatched directory tree — the real data
directory is case-insensitive on macOS and would hide the bug, so the test builds its own),
the full 282-association count, the `PMax`/`PMin` dedup for `122_HYDRO_1` shown above, the
`Natural_Inflow` resolution through `storage.csv` to `212_CSP_1`, and the exact
Generator/Reserve/Area owner-category counts (264/12/6).

Next: [08 — validation and reading the case back](08-validation.md), which ties every stage
together, checks the whole build is deterministic, and reads the finished case back through the
same typed layer chapter 2 introduced.
