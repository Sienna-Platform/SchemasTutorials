"""Demand-side stage: loads, reserves, and reserve service associations,
from ``SourceData/bus.csv``, ``SourceData/reserves.csv``, and
``SourceData/gen.csv``.

Mapping decisions (see CAMPAIGN-FACTS.md R29, R31 for the rulings this
follows):

- One ``PowerLoad`` per bus with nonzero ``MW Load`` (51 of 73 buses).
  ``active_power``/``max_active_power`` both take ``MW Load``,
  ``reactive_power``/``max_reactive_power`` both take ``MVAR Load``; every
  reference ``PowerLoad`` also carries ``conformity=UNDEFINED``.
- Reserve products use ``OnlineReserve`` (the plan's ``VariableReserve``
  does not exist, R14). Both of its time fields are in **minutes**, not the
  source's seconds/hours: ``time_frame = Timeframe (sec) / 60``, and
  ``sustained_time`` is a fixed ``60.0`` for every product (one hour in
  minutes), not the ``3600.0`` the plan says.
- Service associations link each ``OnlineReserve`` to its eligible
  generators. Eligibility is derived by parsing ``reserves.csv``'s
  ``Eligible Device SubCategories`` field directly against gen.csv's own
  ``Category`` column -- the two use the same vocabulary (``Gas CT``,
  ``Oil ST``, ``Solar PV``, ...), so no hardcoded (Unit Type, Fuel) table is
  needed. The region filter parses ``Eligible Regions`` the same way and
  matches against the generator's bus ``Area`` (joined via ``gen.csv``'s
  ``Bus ID`` and ``bus.csv``'s ``Area`` column). Both fields come in two
  shapes -- a bare value (``"1"``) or a parenthesized comma list
  (``"(1,2,3)"``) -- ``_parse_tuple_field`` handles both.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from power_openapi_models.infrastructure_core.models import UnitSystem
from power_openapi_models.operations.models import (
    LoadConformity,
    OnlineReserve,
    PowerLoad,
    ReserveDirection,
)

from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import TopologyIndex

BASE_POWER = 100.0
SECONDS_PER_MINUTE = 60.0
SUSTAINED_TIME = 60.0

DIRECTION_BY_SOURCE: dict[str, ReserveDirection] = {
    "Up": ReserveDirection.UP,
    "Down": ReserveDirection.DOWN,
}


def _parse_tuple_field(raw: str) -> list[str]:
    """Parse a ``reserves.csv`` field that is either a bare value (``"1"``)
    or a parenthesized comma list (``"(1,2,3)"``) into a list of strings.
    """
    text = str(raw).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return [item.strip() for item in text.split(",") if item.strip()]


def add_loads(doc: CaseDocument, source: Path, idx: TopologyIndex) -> None:
    """Add one ``PowerLoad`` per ``source/bus.csv`` row with nonzero
    ``MW Load``.
    """
    bus = pd.read_csv(source / "bus.csv")
    for row in bus.to_dict("records"):
        mw_load = float(row["MW Load"])
        if mw_load == 0.0:
            continue

        bus_number = int(row["Bus ID"])
        if bus_number not in idx.bus_id_by_number:
            raise ValueError(f"bus.csv row {bus_number!r}: unmapped bus in topology index")

        mvar_load = float(row["MVAR Load"])
        load = PowerLoad(
            id=doc.next_id(),
            name=str(row["Bus Name"]),
            available=True,
            bus=idx.bus_id_by_number[bus_number],
            active_power=mw_load,
            max_active_power=mw_load,
            reactive_power=mvar_load,
            max_reactive_power=mvar_load,
            base_power=BASE_POWER,
            power_units=UnitSystem.NATURAL_UNITS,
            conformity=LoadConformity.UNDEFINED,
        )
        doc.add_component(load)


def _eligible_generator_uids(
    gen: pd.DataFrame, area_by_bus_number: dict[int, int], regions: set[int], categories: set[str]
) -> list[str]:
    eligible: list[str] = []
    for row in gen.to_dict("records"):
        if str(row["Category"]) not in categories:
            continue
        bus_number = int(row["Bus ID"])
        if bus_number not in area_by_bus_number:
            raise ValueError(f"gen.csv row {row['GEN UID']!r}: unmapped bus {bus_number!r} in bus.csv")
        if area_by_bus_number[bus_number] not in regions:
            continue
        eligible.append(str(row["GEN UID"]))
    return eligible


def add_reserves(
    doc: CaseDocument, source: Path, idx: TopologyIndex, gen_ids: dict[str, int]
) -> dict[str, int]:
    """Add one ``OnlineReserve`` per ``source/reserves.csv`` row, then one
    ``service_associations`` row per (reserve, eligible generator) pair.
    Returns the reserve id by product name.
    """
    reserves = pd.read_csv(source / "reserves.csv")
    gen = pd.read_csv(source / "gen.csv")
    bus = pd.read_csv(source / "bus.csv")
    area_by_bus_number: dict[int, int] = {
        int(bus_number): int(area) for bus_number, area in zip(bus["Bus ID"], bus["Area"])
    }

    reserve_id_by_product: dict[str, int] = {}
    for row in reserves.to_dict("records"):
        product = str(row["Reserve Product"])
        direction_name = str(row["Direction"])
        direction = DIRECTION_BY_SOURCE.get(direction_name)
        if direction is None:
            raise ValueError(f"reserves.csv row {product!r}: unmapped Direction {direction_name!r}")

        reserve = OnlineReserve(
            id=doc.next_id(),
            name=product,
            available=True,
            time_frame=float(row["Timeframe (sec)"]) / SECONDS_PER_MINUTE,
            requirement=float(row["Requirement (MW)"]),
            sustained_time=SUSTAINED_TIME,
            max_output_fraction=1.0,
            max_participation_factor=1.0,
            deployed_fraction=0.0,
            reserve_direction=direction,
        )
        reserve_id = doc.add_component(reserve)
        reserve_id_by_product[product] = reserve_id

        regions = {int(value) for value in _parse_tuple_field(row["Eligible Regions"])}
        categories = set(_parse_tuple_field(row["Eligible Device SubCategories"]))
        for uid in _eligible_generator_uids(gen, area_by_bus_number, regions, categories):
            if uid not in gen_ids:
                raise ValueError(
                    f"reserves.csv row {product!r}: eligible generator {uid!r} not in gen_ids"
                )
            doc.add_service_association(reserve_id, gen_ids[uid])

    return reserve_id_by_product
