"""The build driver: composes every stage into one ordered pipeline, writes
the document plus its parquet sidecar, and reads a built case back.

Stage order is fixed and load-bearing:

    topology -> branches -> generation -> loads -> reserves -> time series

Every stage mints component ids from the same ``CaseDocument`` counter, and a
later stage's components (an ``Arc``'s buses, a generator's bus, a reserve's
eligible generators, a time-series association's owner) reference ids an
earlier stage minted. The Julia tutorial builds the same case from the same
source data in the same order, so both languages mint an identical id
sequence for a given component — the cross-language equivalence test
(Julia Task 10) depends on this. Changing the order would not break either
language's own build, but it would silently break id parity between them.
"""

from __future__ import annotations

from pathlib import Path

from rts_gmlc_case import data
from rts_gmlc_case.branches import add_branches
from rts_gmlc_case.demand import add_loads, add_reserves
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.sidecar import SidecarWriter
from rts_gmlc_case.timeseries import TimeSeriesOwners, attach_time_series
from rts_gmlc_case.topology import add_topology

SYSTEM_FILENAME = "system.json"


def build_case(case_dir: str | Path) -> CaseDocument:
    """Build the full RTS-GMLC case from the downloaded source data and
    write it into ``case_dir``.

    Runs every stage in the fixed order topology -> branches -> generation ->
    loads -> reserves -> time series, validates the result, then writes
    ``case_dir/system.json`` plus the ``timeseries/`` parquet sidecar.
    Returns the built ``CaseDocument``.
    """
    case_dir = Path(case_dir)
    source = data.rts_source_dir() / "SourceData"

    doc = CaseDocument()

    idx = add_topology(doc, source)
    add_branches(doc, source, idx)
    gen_ids = add_generation(doc, source, idx)
    add_loads(doc, source, idx)
    reserve_ids = add_reserves(doc, source, idx, gen_ids)

    sidecar = SidecarWriter(case_dir)
    owners = TimeSeriesOwners(
        generator_id_by_uid=gen_ids,
        area_id_by_name=idx.area_id_by_name,
        reserve_id_by_product=reserve_ids,
    )
    attach_time_series(doc, source, sidecar, owners)

    doc.validate()

    case_dir.mkdir(parents=True, exist_ok=True)
    doc.write(case_dir / SYSTEM_FILENAME)

    return doc


def read_case(case_dir: str | Path) -> CaseDocument:
    """Read a case previously written by ``build_case`` back from
    ``case_dir``.

    Re-parses every component bucket through its pydantic class
    (``CaseDocument.typed_components()``) and re-runs ``validate()``, so a
    silent alias or enum-coercion bug in either the write or the read path
    surfaces here rather than downstream.
    """
    case_dir = Path(case_dir)
    doc = CaseDocument.read(case_dir / SYSTEM_FILENAME)
    doc.typed_components()
    doc.validate()
    return doc
