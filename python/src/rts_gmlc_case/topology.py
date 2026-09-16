"""Topology stage: areas, load zones, buses, and bus shunts, from
``SourceData/bus.csv``.

Mapping decisions (see CAMPAIGN-FACTS.md R3, R12a for the rulings this
follows):

- One ``Area`` per distinct ``Area`` value, one ``LoadZone`` per distinct
  ``Zone`` value — both added in sorted numeric order so ids are
  deterministic across languages. RTS has 3 areas and 21 zones; the 21
  intentionally does not collapse to 3 (a distinct-``Zone`` mapping keeps
  information a per-``Area`` mapping would discard).
- Every component sets ``power_units=UnitSystem.NATURAL_UNITS`` and an
  explicit ``base_power`` (there is no document-level unit system).
- ``LoadZone.peak_active_power``/``peak_reactive_power`` are the per-zone
  sums of ``MW Load``/``MVAR Load`` over member buses; ``Area``'s optional
  peak fields (plus ``load_response=0.0``) are the per-area sums likewise.
  The zone sums are genuinely per-``Zone`` and differ from the PTDP
  reference's per-``Area``-derived load zones — that divergence is
  intentional (21 zones, not 3).
- Three buses (106 Alber, 206 Bajer, 306 Camus) carry a nonzero
  ``MVAR Shunt B``; each gets one ``FixedAdmittance`` rather than being
  silently dropped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from power_openapi_models.core.models import (
    ACBus,
    ACBusType,
    Area,
    LoadZone,
    ShuntAdmittanceUnitBasis,
)
from power_openapi_models.infrastructure_core.models import (
    ComplexNumber,
    MinMax,
    UnitSystem,
)
from power_openapi_models.operations.models import FixedAdmittance

from rts_gmlc_case.document import CaseDocument

BASE_POWER = 100.0
VOLTAGE_LIMITS = MinMax(min=0.95, max=1.05)


@dataclass
class TopologyIndex:
    """Cross-reference from source-data keys to minted component ids,
    consumed by later stages (Task 4's branches and beyond).
    """

    bus_id_by_number: dict[int, int]
    area_id_by_name: dict[str, int]
    zone_id_by_name: dict[str, int]


def _normalize_bustype(raw: str) -> ACBusType:
    if raw == "Ref":
        return ACBusType.REF
    return ACBusType(raw.upper())


def add_topology(doc: CaseDocument, source: Path) -> TopologyIndex:
    """Add ``Area``, ``LoadZone``, ``ACBus``, and ``FixedAdmittance``
    components from ``source/bus.csv`` to ``doc``. Returns a
    ``TopologyIndex`` mapping source keys to minted ids.
    """
    bus = pd.read_csv(source / "bus.csv")

    area_load = bus.groupby("Area")[["MW Load", "MVAR Load"]].sum()
    zone_load = bus.groupby("Zone")[["MW Load", "MVAR Load"]].sum()

    area_id_by_name: dict[str, int] = {}
    for area_value in sorted(bus["Area"].unique()):
        name = str(int(area_value))
        area = Area(
            id=doc.next_id(),
            name=name,
            peak_active_power=float(area_load.loc[area_value, "MW Load"]),
            peak_reactive_power=float(area_load.loc[area_value, "MVAR Load"]),
            load_response=0.0,
            base_power=BASE_POWER,
            power_units=UnitSystem.NATURAL_UNITS,
        )
        area_id_by_name[name] = doc.add_component(area)

    zone_id_by_name: dict[str, int] = {}
    for zone_value in sorted(bus["Zone"].unique()):
        name = str(int(zone_value))
        zone = LoadZone(
            id=doc.next_id(),
            name=name,
            peak_active_power=float(zone_load.loc[zone_value, "MW Load"]),
            peak_reactive_power=float(zone_load.loc[zone_value, "MVAR Load"]),
            base_power=BASE_POWER,
            power_units=UnitSystem.NATURAL_UNITS,
        )
        zone_id_by_name[name] = doc.add_component(zone)

    bus_id_by_number: dict[int, int] = {}
    for row in bus.to_dict("records"):
        bus_number = int(row["Bus ID"])
        area_name = str(int(row["Area"]))
        zone_name = str(int(row["Zone"]))
        if area_name not in area_id_by_name:
            raise ValueError(f"bus {bus_number}: unmapped area {area_name!r}")
        if zone_name not in zone_id_by_name:
            raise ValueError(f"bus {bus_number}: unmapped zone {zone_name!r}")

        acbus = ACBus(
            id=doc.next_id(),
            number=bus_number,
            name=str(row["Bus Name"]),
            available=True,
            bustype=_normalize_bustype(str(row["Bus Type"])),
            angle=math.radians(float(row["V Angle"])),
            magnitude=float(row["V Mag"]),
            voltage_limits=VOLTAGE_LIMITS,
            base_voltage=float(row["BaseKV"]),
            area=area_id_by_name[area_name],
            load_zone=zone_id_by_name[zone_name],
        )
        bus_id = doc.add_component(acbus)
        bus_id_by_number[bus_number] = bus_id

        mw_shunt_g = float(row["MW Shunt G"])
        mvar_shunt_b = float(row["MVAR Shunt B"])
        if mw_shunt_g != 0.0 or mvar_shunt_b != 0.0:
            doc.add_component(
                FixedAdmittance(
                    id=doc.next_id(),
                    name=f"{row['Bus Name']}_shunt",
                    available=True,
                    bus=bus_id,
                    Y=ComplexNumber(real=mw_shunt_g, imag=mvar_shunt_b),
                    base_power=BASE_POWER,
                    admittance_units=ShuntAdmittanceUnitBasis.NATURAL_UNITS,
                )
            )

    return TopologyIndex(
        bus_id_by_number=bus_id_by_number,
        area_id_by_name=area_id_by_name,
        zone_id_by_name=zone_id_by_name,
    )
