# rts-gmlc-case

Builds the RTS-GMLC power system as a portable OpenAPI case document: one JSON file describing
buses, branches, generators, loads, and reserves by integer id, plus a folder of content-addressed
parquet files holding every time series. The format is language-neutral — nothing about reading
the result depends on Python.

## Setup

```sh
uv sync
```

This project depends on `power-openapi-models`, installed as an editable path
dependency from `../../power-openapi-models` (a sibling checkout in this
workspace). Consumers outside this workspace should instead run:

```sh
pip install power-openapi-models
```

## Source data

`rts_gmlc_case.data.rts_source_dir()` downloads and caches the pinned
RTS-GMLC v0.2.2 tarball into `<repo-root>/data/RTS-GMLC/`, verifies its
sha256 checksum, and returns the `RTS_Data` directory. The download runs
once; subsequent calls reuse the cached, extracted files.

## Build the case

```sh
uv run python build_rts.py <output-dir>
```

Reads all seven source tables and all 282 time-series pointers; writes `<output-dir>/system.json`
plus `<output-dir>/timeseries/*.parquet`. This is the one expensive command in this project — it
reads every time-series profile in the dataset, some over 100k rows — so don't run it more than
you need to.

## Tests

```sh
uv run pytest
```

Five tests (each a full build) are marked `slow`; skip them for a fast check of everything else:

```sh
uv run pytest -m "not slow"
```

## Tutorial

Read in order — each stage builds on the ids and conventions the last one established:

1. [Setup and pinned data](docs/01-setup.md)
2. [The document](docs/02-document.md)
3. [Topology](docs/03-topology.md)
4. [Branches](docs/04-branches.md)
5. [Generators and costs](docs/05-generation.md)
6. [Loads, storage, reserves](docs/06-demand.md)
7. [Time series and the parquet sidecar](docs/07-timeseries.md)
8. [Validation and reading the case back](docs/08-validation.md)
