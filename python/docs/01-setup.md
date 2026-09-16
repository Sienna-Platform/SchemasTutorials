# 1. Setup and pinned data

This tutorial builds a real 73-bus power system — RTS-GMLC — into a single portable case
document: one JSON file plus a folder of value files. The result is language-neutral: nothing in
the output format depends on Python or on this tutorial's tooling — any reader can parse the JSON
and read the value files with whatever they already use.

## Install

```sh
uv sync
```

`pyproject.toml` declares one real dependency beyond pandas/pyarrow/pydantic:

```toml
dependencies = [
    "pandas>=3.0.5",
    "power-openapi-models",
    "pyarrow>=25.0.1",
    "pydantic>=2.13.5",
]
```

`power-openapi-models` is the package that defines every component type this tutorial uses —
buses, branches, generators, reserves, time-series associations. This project depends on it as
an editable local path (a sibling checkout); outside this workspace, installing it is a plain

```sh
pip install power-openapi-models
```

Nothing else here is package-specific. The rest of this tutorial is: read seven CSV tables, and
turn each row into one typed component.

## The source data

RTS-GMLC ships as a tarball of CSV tables and time-series files. `rts_gmlc_case.data.rts_source_dir()`
downloads and caches it:

```python
from rts_gmlc_case import data
data.URL
# 'https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz'
data.SHA256
# 'f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2'
```

The version and checksum are pinned literals — every build of this tutorial's case starts from
byte-identical source data. `rts_source_dir()` downloads once into `<repo-root>/data/RTS-GMLC/`,
verifies the SHA-256 of the tarball before extracting it, and on every later call just returns
the already-extracted directory. It never silently redownloads over an existing, incomplete
cache — if the required files are missing, it raises and tells you to delete the directory
first.

Two directories matter inside the extracted tree:

```python
data.REQUIRED_SOURCE_TABLES
# ('bus.csv', 'branch.csv', 'gen.csv', 'dc_branch.csv',
#  'reserves.csv', 'storage.csv', 'timeseries_pointers.csv')
data.TIMESERIES_DATA
# 'timeseries_data_files'
```

`SourceData/` holds the seven CSV tables every later chapter reads. `timeseries_data_files/`
holds the actual hourly/5-minute profiles those tables point at — chapter 7 reads those.

## What to check

```sh
uv run pytest -q tests/test_data.py
```
```
..                                                                       [100%]
2 passed in 0.09s
```

The first test asserts every one of the seven required tables and the time-series directory
exist under the cached path. The second builds a deliberately incomplete cache and confirms the
error message names every missing file by name — a build that dies on missing data should say
exactly what's missing, not just that something failed.

Next: [02 — the document](02-document.md), which introduces the container everything else adds
components to.
