"""Investments existing-device and supply-technology stage: one
``SupplyTechnology`` candidate plus one ``ExistingDevices`` supplemental
attribute per technology class, built from the ReEDS-style generator
database (``capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv``
under ``investments_source_dir()``). Every one of that file's 155 rows has
``IsExistUnit == True`` (no candidate rows to filter out); this module
asserts that rather than assuming it.

Which ``tech`` classes become candidates (the plan's exact words: *"the
technology classes the supply curves cover (``upv``, ``wind-ons``), plus
thermal and hydro classes from the generator database"*), read as a set
union — ``POWER_SYSTEMS_TYPE_BY_CLASS`` below is exactly that literal
reading: ``upv``/``wind-ons`` (the two with a supply-curve file),
``gas-cc``/``gas-ct``/``o-g-s``/``coalolduns``/``nuclear`` (thermal), and
``hydED``/``hydEND`` (hydro) = 9 classes. ``distpv`` and ``csp-ns`` are
deliberately excluded — neither has a supply curve nor counts as
thermal/hydro. ``battery_4`` is excluded too: it becomes a
``StorageTechnology`` in Task E3, not a ``SupplyTechnology``.

``power_systems_type`` (R39) is the exact PSY type name the *operations*
campaign would build this class's devices as: ``ThermalStandard`` for the
5 thermal classes, ``HydroDispatch`` for the 2 hydro classes,
``RenewableDispatch`` for ``upv``/``wind-ons``.

``region`` is the sorted list of zone ids (via the investments topology
stage's ``zone_id_by_bus_number``) where at least one existing device of
that class sits — the union of zones its ``ExistingDevices`` members
belong to, not an assumption of zone-universality.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from power_openapi_models.investments.models import ExistingDevices, SupplyTechnology

from rts_gmlc_case.document import PortfolioCase
from rts_gmlc_case.generation import FUEL_BY_SOURCE
from rts_gmlc_case.investments.costs import (
    capital_cost_curve,
    capital_costs_for,
    financial_data_for,
)
from rts_gmlc_case.investments.topology import InvestmentTopologyIndex
from rts_gmlc_case.topology import TopologyIndex

GENERATOR_DATABASE = "capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv"

# The 9 SupplyTechnology candidate classes, mapped to the exact PSY
# component type name the operations campaign builds for that class (R39).
POWER_SYSTEMS_TYPE_BY_CLASS: dict[str, str] = {
    "gas-cc": "ThermalStandard",
    "gas-ct": "ThermalStandard",
    "o-g-s": "ThermalStandard",
    "coalolduns": "ThermalStandard",
    "nuclear": "ThermalStandard",
    "hydED": "HydroDispatch",
    "hydEND": "HydroDispatch",
    "upv": "RenewableDispatch",
    "wind-ons": "RenewableDispatch",
}

# SupplyTechnology.fuel is only meaningful for thermal classes. Fuel is a
# clean per-class constant in the source (o-g-s is Oil for every row despite
# spanning Unit Type {CT, STEAM}). Non-thermal classes (hydED, hydEND, upv,
# wind-ons) are absent here on purpose and left with fuel=None: their source
# Fuel values (Hydro, Solar, Wind) have no FUEL_BY_SOURCE entry and don't
# need one.
FUEL_NAME_BY_CLASS: dict[str, str] = {
    "gas-cc": "NG",
    "gas-ct": "NG",
    "o-g-s": "Oil",
    "coalolduns": "Coal",
    "nuclear": "Nuclear",
}


def add_supply_technologies(
    doc: PortfolioCase,
    source: Path,
    idx: TopologyIndex,
    inv_idx: InvestmentTopologyIndex,
) -> dict[str, int]:
    """Add one ``SupplyTechnology`` plus one ``ExistingDevices`` supplemental
    attribute per class in ``POWER_SYSTEMS_TYPE_BY_CLASS``, in sorted
    class-name order for determinism. Returns a mapping from class name to
    the minted ``SupplyTechnology`` id (later tasks need this).
    """
    del idx  # unused: no cross-check against the operations TopologyIndex is needed by this stage.
    gen_db = pd.read_csv(source / GENERATOR_DATABASE)
    if not gen_db["IsExistUnit"].all():
        raise ValueError(
            f"{GENERATOR_DATABASE}: expected every row to have IsExistUnit == True "
            "(this module does not filter candidate rows)"
        )

    technology_id_by_class: dict[str, int] = {}
    for tech_class in sorted(POWER_SYSTEMS_TYPE_BY_CLASS):
        rows = gen_db[gen_db["tech"] == tech_class]
        if rows.empty:
            raise ValueError(f"tech class {tech_class!r}: no rows in {GENERATOR_DATABASE}")

        device_uids = sorted(str(uid) for uid in rows["GEN UID"])
        zone_ids = sorted(
            {inv_idx.zone_id_by_bus_number[int(bus_number)] for bus_number in rows["Bus ID"]}
        )

        fuel_name = FUEL_NAME_BY_CLASS.get(tech_class)
        fuel = [FUEL_BY_SOURCE[fuel_name]] if fuel_name is not None else None

        technology = SupplyTechnology(
            id=doc.next_id(),
            name=tech_class,
            power_systems_type=POWER_SYSTEMS_TYPE_BY_CLASS[tech_class],
            region=zone_ids,
            # Explicit None, not the field's own default: SupplyTechnology's
            # `prime_mover_type` default is the bare string "OT" rather than
            # `PrimeMovers.OT` (an upstream power_openapi_models codegen
            # quirk), which trips a pydantic serializer UserWarning on every
            # `model_dump` unless overridden. Nothing in this task requires
            # a prime mover value (o-g-s spans Unit Type {CT, STEAM}, so a
            # single deterministic choice isn't even available for it), so
            # None is both correct and warning-free here.
            prime_mover_type=None,
            fuel=fuel,
            capital_costs=capital_costs_for(capital_cost_curve(tech_class)),
            financial_data=financial_data_for(tech_class),
        )
        technology_id = doc.add_component(technology)
        technology_id_by_class[tech_class] = technology_id

        existing_devices = ExistingDevices(id=doc.next_id(), existing_devices=device_uids)
        doc.add_supplemental_attribute(
            existing_devices,
            component_id=technology_id,
            component_type="SupplyTechnology",
        )

    return technology_id_by_class
