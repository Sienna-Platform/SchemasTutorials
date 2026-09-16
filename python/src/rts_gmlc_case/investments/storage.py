"""Investments storage-technology stage: one ``StorageTechnology`` candidate
built from the same ReEDS-style generator database E2 reads
(``capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv``
under ``investments_source_dir()``). Exactly one row has ``tech ==
"battery_4"`` (``GEN UID`` ``"313_STORAGE_1"``, ``Bus ID`` 313, ``cap`` 50.0
MW, ``Storage Roundtrip Efficiency`` 85) — this module asserts that count
rather than assuming it.

``power_systems_type`` is ``"EnergyReservoirStorage"`` (R39's 4th string —
not produced by any of E2's 9 ``SupplyTechnology`` classes, so this is
where it first appears in the document).

``efficiency`` reuses the exact split-roundtrip-efficiency formula
``rts_gmlc_case.generation._build_energy_reservoir_storage`` already uses
for the operations-side ``EnergyReservoirStorage``: ``sqrt(roundtrip /
100.0)`` applied identically to both legs, read from the CSV row (not
hardcoded). ``storage_tech`` reuses that same function's
``StorageTech.OTHER_CHEM`` choice for battery storage (same field meaning,
different field name: ``storage_technology_type`` there,
``storage_tech`` here).

Capacity: ``cap`` (50.0 MW) is a power figure, so it becomes
``capacity_limits_charge``/``capacity_limits_discharge`` (``MinMax(min=0.0,
max=cap)``), not ``capacity_limits_energy`` — no energy (MWh) capacity
figure exists in this dataset, so ``capacity_limits_energy`` is left
``None`` rather than fabricated.

``duration_limits`` is left ``None``: both
``storagedata/storage_duration_pshdata.csv`` and
``storagedata/storinmaxfrac.csv`` are header-only (zero data rows) in this
dataset snapshot — a test in ``tests/test_investments_storage.py`` reads
both fresh and asserts this, so a future dataset refresh that adds real
duration data is caught rather than silently leaving this field wrong.

``prime_mover_type`` is set explicitly to ``PrimeMovers.BA`` rather than
left at the field's default — see the module-level note in
``rts_gmlc_case.investments.technologies`` about the same upstream
``power_openapi_models`` codegen quirk (the field's Pydantic default is the
bare string ``"OT"``, not an enum member, which trips a pydantic
serializer ``UserWarning`` unless overridden). Unlike ``SupplyTechnology``'s
``o-g-s`` case, this candidate always models a battery, so ``BA`` is not
just warning-avoidance — it is the correct value.

Capital costs, operation cost, and financial data are external/
illustrative (R37) — see ``rts_gmlc_case.investments.costs`` for the
figures and their provenance framing.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from power_openapi_models.core.models import PrimeMovers, StorageTech
from power_openapi_models.infrastructure_core.models import InOut, MinMax
from power_openapi_models.investments.models import ExistingDevices, StorageTechnology

from rts_gmlc_case.document import PortfolioCase
from rts_gmlc_case.investments.costs import (
    battery_capital_costs,
    battery_operation_cost,
    financial_data_for,
)
from rts_gmlc_case.investments.technologies import GENERATOR_DATABASE
from rts_gmlc_case.investments.topology import InvestmentTopologyIndex

BATTERY_TECH_CLASS = "battery_4"


def add_storage_technologies(
    doc: PortfolioCase,
    source: Path,
    inv_idx: InvestmentTopologyIndex,
) -> dict[str, int]:
    """Add one ``StorageTechnology`` (class ``"battery_4"``) plus one
    ``ExistingDevices`` supplemental attribute to ``doc``. Returns a mapping
    from class name to the minted ``StorageTechnology`` id — shaped like
    ``add_supply_technologies``'s return even though there's only one class
    today.
    """
    gen_db = pd.read_csv(source / GENERATOR_DATABASE)
    rows = gen_db[gen_db["tech"] == BATTERY_TECH_CLASS]
    if len(rows) != 1:
        raise ValueError(
            f"expected exactly 1 {BATTERY_TECH_CLASS!r} row in {GENERATOR_DATABASE}, "
            f"found {len(rows)}"
        )

    device_uids = sorted(str(uid) for uid in rows["GEN UID"])
    zone_ids = sorted(
        {inv_idx.zone_id_by_bus_number[int(bus_number)] for bus_number in rows["Bus ID"]}
    )

    row = rows.iloc[0]
    cap_mw = float(row["cap"])
    leg_efficiency = math.sqrt(float(row["Storage Roundtrip Efficiency"]) / 100.0)

    capital_costs = battery_capital_costs()

    technology = StorageTechnology(
        id=doc.next_id(),
        name=BATTERY_TECH_CLASS,
        available=True,
        power_systems_type="EnergyReservoirStorage",
        region=zone_ids,
        prime_mover_type=PrimeMovers.BA,
        storage_tech=StorageTech.OTHER_CHEM,
        efficiency=InOut(**{"in": leg_efficiency, "out": leg_efficiency}),
        capacity_limits_charge=MinMax(min=0.0, max=cap_mw),
        capacity_limits_discharge=MinMax(min=0.0, max=cap_mw),
        capacity_limits_energy=None,
        duration_limits=None,
        capital_costs=capital_costs,
        operation_costs=battery_operation_cost(),
        financial_data=financial_data_for(BATTERY_TECH_CLASS),
    )
    technology_id = doc.add_component(technology)

    existing_devices = ExistingDevices(id=doc.next_id(), existing_devices=device_uids)
    doc.add_supplemental_attribute(
        existing_devices,
        component_id=technology_id,
        component_type="StorageTechnology",
    )

    return {BATTERY_TECH_CLASS: technology_id}
