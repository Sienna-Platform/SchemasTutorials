"""Investments topology stage: the cross-reference later investment stages
use to point their ``region`` fields at components that already exist.

**This stage adds nothing to the document.** It is a chapter about a gap.

SiennaSchemas 0.1.0 defines no ``Node`` and no ``Zone`` — the investments
group has no topology component at all — while
``PowerSystemsInvestmentsPortfolios.jl`` still has both structs. The schema is
the side that is behind, and until it catches up a portfolio cannot mint its
own topology.

What it can do is reuse the operations topology, which is already in the base
system. Every investments technology's ``region`` is a ``list[int]`` described
as *"Location where the component applies. Can be a zone or node"* — a list of
component ids with no declared target type. So this stage points those ids at
the operations components that carry the same meaning:

- a *node* is the ``ACBus`` minted by ``rts_gmlc_case.topology`` (73 total),
- a *zone* is the ``Area`` minted there too (3 total: ``"1"``, ``"2"``,
  ``"3"``).

Zones are RTS *Areas*, **not** ``bus.csv``'s ``Zone`` column (21 values, which
is what the operations ``LoadZone`` models) and **not** ``hierarchy_rts.csv``'s
``ba`` column (5 ReEDS balancing areas).

An earlier draft of this chapter also emitted a ``TopologyMapping``
supplemental attribute per zone, listing its member bus names. That is dropped:
once a zone *is* an ``Area``, the membership is already recorded by each
``ACBus``'s own ``area`` field, and a ``TopologyMapping`` would only restate it
in a second place that nothing keeps in sync. It would also have to attach to a
component in the *other* document, which the Julia container rejects outright.

``investments_source_dir()``'s output is accepted as the ``source`` parameter
for signature symmetry with later investment stages (E2+) that do read from it,
but this stage reads nothing under it — every value comes from the operations
``bus.csv`` and the ``TopologyIndex`` it is handed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import PortfolioCase
from rts_gmlc_case.topology import TopologyIndex


@dataclass
class InvestmentTopologyIndex:
    """Cross-reference from source-data keys to the operations component ids
    that investments ``region`` fields point at, consumed by later stages
    (E2+).

    The ids are operations ``ACBus`` and ``Area`` ids, living in the base
    system — not ids of any investments component. See the module docstring.
    """

    node_id_by_bus_number: dict[int, int]
    zone_id_by_name: dict[str, int]
    zone_id_by_bus_number: dict[int, int]


def add_investment_topology(
    doc: PortfolioCase, source: Path, idx: TopologyIndex
) -> InvestmentTopologyIndex:
    """Return the ``InvestmentTopologyIndex`` later stages use as ``region``
    targets. Adds nothing to ``doc`` — see the module docstring.

    ``doc`` is still taken, and the bus/area consistency below still checked,
    because both are what a reader would expect of this stage, and because the
    check catches an operations/investments mismatch here rather than three
    stages later.
    """
    del doc  # nothing to add: the schema has no investments topology component.
    del source  # unused: see module docstring.
    bus = pd.read_csv(data.rts_source_dir() / "SourceData" / "bus.csv")

    zone_id_by_bus_number: dict[int, int] = {}
    for row in bus.to_dict("records"):
        bus_number = int(row["Bus ID"])
        if bus_number not in idx.bus_id_by_number:
            raise ValueError(f"bus {bus_number}: not present in operations TopologyIndex")
        zone_name = str(int(row["Area"]))
        if zone_name not in idx.area_id_by_name:
            raise ValueError(f"bus {bus_number}: unmapped area {zone_name!r}")
        zone_id_by_bus_number[bus_number] = idx.area_id_by_name[zone_name]

    return InvestmentTopologyIndex(
        node_id_by_bus_number=dict(idx.bus_id_by_number),
        zone_id_by_name=dict(idx.area_id_by_name),
        zone_id_by_bus_number=zone_id_by_bus_number,
    )
