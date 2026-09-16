"""Investments demand-side stage: one ``DemandRequirement`` per zone, plus
its hourly load-requirement time series, built from
``loaddata/RTS_DA_regional_load.csv`` (under ``investments_source_dir()``).

Mapping decisions:

- One ``DemandRequirement`` per zone (3 total, one per RTS Area) — not per
  bus. The CSV's three load columns are named ``"1"``, ``"2"``, ``"3"``,
  matching the zone names E1's ``InvestmentTopologyIndex`` already keys on,
  so no bus-level disaggregation is needed or possible from this file.
- ``power_systems_type = "PowerLoad"``: confirmed by reading
  ``rts_gmlc_case.demand``'s ``add_loads``, which builds the operations
  campaign's load components as ``PowerLoad``. This extends the R39 "exact
  PSY type name this campaign emits" principle from the generation side
  (E2) to the demand side.
- ``conformity`` is left at the schema's own default (``"UNDEFINED"``),
  matching the operations ``PowerLoad``'s own ``LoadConformity.UNDEFINED``
  convention.
- ``value_of_lost_load`` is required but has no dataset-sourced figure in
  scope for this task; see ``VALUE_OF_LOST_LOAD`` below.
- Everything else (``new_demand_mw``, ``growth_rate``,
  ``new_construction_year``, ``unserved_demand_curve``)
  is left at its schema default: nothing in this task's inputs populates
  any of them.
- The time series reuses ``rts_gmlc_case.timeseries``'s already-public
  ``RESOLUTION_BY_SIMULATION`` and ``read_profile`` directly (Layout A —
  one ``Period``-resetting-daily row per hour, the zone name as the column
  selector) — no re-derivation of either. The association is built
  field-for-field to match the shape ``rts_gmlc_case.timeseries``'s
  ``attach_time_series`` already builds for other owners.
"""

from __future__ import annotations

from pathlib import Path

from power_openapi_models.operations.models import LoadConformity
from power_openapi_models.investments.models import DemandRequirement
from power_openapi_models.timeseries.models import (
    OwnerCategory,
    SingleTimeSeries,
    TimeSeriesAssociation,
)

from rts_gmlc_case.document import PortfolioCase
from rts_gmlc_case.investments.topology import InvestmentTopologyIndex
from rts_gmlc_case.sidecar import SidecarWriter
from rts_gmlc_case.timeseries import RESOLUTION_BY_SIMULATION, read_profile

LOAD_DATA_FILE = "loaddata/RTS_DA_regional_load.csv"

# Illustrative VOLL (value of lost load), USD/MWh. Not sourced from this
# dataset -- the plan classifies `value_of_lost_load` as unsourced/external,
# so this is a commonly-cited illustrative figure for a capacity-expansion
# worked example, not a lookup. It happens to land near scalars.csv's
# `cost_dropped_load` row (10000, 2004$/MWh) -- that is coincidental
# plausibility, not a citation: that field is explicitly "(only allowed in
# historical years)" and the plan does not treat it as a sourced VOLL.
VALUE_OF_LOST_LOAD = 9_000.0


def add_demand_requirements(
    doc: PortfolioCase,
    source: Path,
    sidecar: SidecarWriter,
    inv_idx: InvestmentTopologyIndex,
) -> dict[str, int]:
    """Add one ``DemandRequirement`` per zone (sorted zone-name order) plus
    its hourly ``requirement`` time series, read from
    ``source/loaddata/RTS_DA_regional_load.csv``. Returns the minted
    ``DemandRequirement`` id by zone name.
    """
    csv_path = source / LOAD_DATA_FILE
    resolution_str, resolution_delta = RESOLUTION_BY_SIMULATION["DAY_AHEAD"]

    demand_requirement_id_by_zone: dict[str, int] = {}
    for zone_name in sorted(inv_idx.zone_id_by_name, key=int):
        timestamps, values = read_profile(csv_path, zone_name, resolution_delta)

        requirement = DemandRequirement(
            id=doc.next_id(),
            name=zone_name,
            power_systems_type="PowerLoad",
            region=[inv_idx.zone_id_by_name[zone_name]],
            value_of_lost_load=VALUE_OF_LOST_LOAD,
            # Set explicitly rather than left to its schema default: the document
            # omits what this build never set, and the Julia side sets it too.
            conformity=LoadConformity.UNDEFINED,
        )
        requirement_id = doc.add_component(requirement)
        demand_requirement_id_by_zone[zone_name] = requirement_id

        uri, digest = sidecar.write(timestamps, values)

        association = SingleTimeSeries(
            association_id=doc.next_id(),
            owner_id=requirement_id,
            owner_type="DemandRequirement",
            owner_category=OwnerCategory.Component,
            time_series_type="SingleTimeSeries",
            name="requirement",
            features={},
            uri=uri,
            data_hash=digest,
            element_type="f64",
            element_shape=[],
            array_shape=[len(values)],
            units="MW",
            quantity_kind="requirement",
            unit_system="NATURAL_UNITS",
            time_reference="zoneless",
            initial_timestamp=timestamps[0],
            resolution=resolution_str,
            length=len(values),
        )
        doc.document.time_series_associations.append(TimeSeriesAssociation(association))

    return demand_requirement_id_by_zone
