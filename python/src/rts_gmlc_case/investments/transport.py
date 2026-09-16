"""Investments transport-technology stage: one ``NodalACTransportTechnology``
per unique existing AC corridor and one ``NodalHVDCTransportTechnology`` for
the system's single existing HVDC link.

AC data: ``transmission/transmission_capacity_init_AC_rts_nodal.csv`` (120
rows: ``interface``, ``From_Bus``, ``To_Bus``, ``MW_f0``, ``MW_r0`` — bus
ids in ``bXXX`` form, e.g. ``b101``; the leading ``b`` is stripped to join
against ``InvestmentTopologyIndex.node_id_by_bus_number``) and
``transmission/transmission_distance_cost_500kVac_nodal.csv`` (108 rows:
``r``, ``rr``, ``length_miles``, ``USD2004perMW``, same ``bXXX`` join key
on ``r``/``rr`` matching ``From_Bus``/``To_Bus``).

**Duplicate-pair resolution.** The capacity file has 120 rows but only 108
distinct ``(From_Bus, To_Bus)`` pairs — 12 pairs each appear as two
*exactly identical* rows (same ``MW_f0``/``MW_r0``), with no circuit-id
column to disambiguate them (unlike operations ``branch.csv``'s
``Circuit``). This module builds **one ``NodalACTransportTechnology`` per
unique pair (108 total)**, summing ``MW_f0`` across duplicate rows for
that pair — read as combined parallel-circuit capacity on one investable
corridor. Every capacity-file row has ``MW_f0 == MW_r0`` (asserted below),
so only ``MW_f0`` is used. The cost file's 108 rows are exactly the
capacity file's 108 unique pairs, one row each — no join gaps either way.

HVDC data: ``transmission/transmission_capacity_init_nonAC_nodal.csv`` (1
row: ``b113,b316,LCC,100``) and
``transmission/transmission_distance_cost_500kVdc_nodal.csv`` (1 matching
row, 70 miles, ``USD2004perMW`` 644267.96). One
``NodalHVDCTransportTechnology`` component.

``capital_costs`` on both technologies is a genuinely dataset-sourced flat
linear ``ValueCurve`` (``rts_gmlc_case.investments.costs.
flat_linear_value_curve``) built from ``USD2004perMW`` — 2004 USD, **no
inflation adjustment applied** (a real limitation of this dataset, not
silently corrected here). Unlike the illustrative supply/storage capital
costs, this figure is not routed through the "illustrative" framing.

``financial_data.capital_recovery_period`` is genuinely sourced too: 40
years, from ``scalars.csv``'s ``trans_crp`` row — see
``rts_gmlc_case.investments.costs.transport_financial_data`` for the exact
citation. That helper's other 5 ``TechnologyFinancialData`` fields have no
transmission-specific source in this dataset and are illustrative.

``power_systems_type`` follows the same R39 convention E2 established
(the exact PSY type name the *operations* campaign would build this
class's devices as, per ``rts_gmlc_case.branches``): ``"Line"`` for AC
corridors, ``"TwoTerminalGenericHVDCLine"`` for the HVDC link. The brief's
field list for this stage does not name this field explicitly (unlike
Part A's ``StorageTechnology.power_systems_type``); it is required by the
schema, so this is this module's own R39-consistent choice.

``resistance``/``reactance``/``voltage``/``unit_size`` on
``NodalACTransportTechnology``, and ``line_loss`` on
``NodalHVDCTransportTechnology``, have no backing dataset field at this
stage and are left at their schema defaults (``0.0`` / ``None``) rather
than invented.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from power_openapi_models.infrastructure_core.models import MinMax
from power_openapi_models.investments.models import (
    NodalACTransportTechnology,
    NodalHVDCTransportTechnology,
)

from rts_gmlc_case.document import PortfolioCase
from rts_gmlc_case.investments.costs import (
    capital_costs_for,
    flat_linear_value_curve,
    transport_financial_data,
)
from rts_gmlc_case.investments.topology import InvestmentTopologyIndex

AC_CAPACITY_FILE = "transmission/transmission_capacity_init_AC_rts_nodal.csv"
AC_COST_FILE = "transmission/transmission_distance_cost_500kVac_nodal.csv"
HVDC_CAPACITY_FILE = "transmission/transmission_capacity_init_nonAC_nodal.csv"
HVDC_COST_FILE = "transmission/transmission_distance_cost_500kVdc_nodal.csv"


def _bus_number(bus_label: str) -> int:
    """Strip the leading ``b`` from a ``bXXX``-form bus id string, e.g.
    ``"b101"`` -> ``101``.
    """
    return int(str(bus_label).lstrip("b"))


def _add_ac_transport_technologies(
    doc: PortfolioCase, source: Path, inv_idx: InvestmentTopologyIndex
) -> dict[tuple[int, int], int]:
    capacity = pd.read_csv(source / AC_CAPACITY_FILE)
    if not (capacity["MW_f0"] == capacity["MW_r0"]).all():
        raise ValueError(f"{AC_CAPACITY_FILE}: expected MW_f0 == MW_r0 on every row")

    summed_capacity = (
        capacity.groupby(["From_Bus", "To_Bus"])["MW_f0"]
        .sum()
        .reset_index()
        .sort_values(["From_Bus", "To_Bus"])
    )

    cost = pd.read_csv(source / AC_COST_FILE)
    if cost.duplicated(subset=["r", "rr"]).any():
        raise ValueError(f"{AC_COST_FILE}: expected exactly one row per (r, rr) pair")
    cost_by_pair = {
        (row["r"], row["rr"]): float(row["USD2004perMW"]) for row in cost.to_dict("records")
    }

    technology_id_by_bus_pair: dict[tuple[int, int], int] = {}
    for row in summed_capacity.to_dict("records"):
        from_bus_label = str(row["From_Bus"])
        to_bus_label = str(row["To_Bus"])
        pair = (from_bus_label, to_bus_label)
        if pair not in cost_by_pair:
            raise ValueError(f"{AC_COST_FILE}: no cost row for pair {pair}")

        start_bus = _bus_number(from_bus_label)
        end_bus = _bus_number(to_bus_label)

        technology = NodalACTransportTechnology(
            id=doc.next_id(),
            name=f"AC_{start_bus}_{end_bus}",
            available=True,
            power_systems_type="Line",
            start_node=inv_idx.node_id_by_bus_number[start_bus],
            end_node=inv_idx.node_id_by_bus_number[end_bus],
            capacity_limits=MinMax(min=0.0, max=float(row["MW_f0"])),
            # resistance/reactance/voltage/unit_size carry a 0.0 default in the schema.
            # Set explicitly, not left unset: the document now omits what was never set,
            # and both languages should record the same values.
            resistance=0.0,
            reactance=0.0,
            voltage=0.0,
            unit_size=0.0,
            capital_costs=capital_costs_for(flat_linear_value_curve(cost_by_pair[pair])),
            financial_data=transport_financial_data(),
        )
        technology_id = doc.add_component(technology)
        technology_id_by_bus_pair[(start_bus, end_bus)] = technology_id

    return technology_id_by_bus_pair


def _add_hvdc_transport_technologies(
    doc: PortfolioCase, source: Path, inv_idx: InvestmentTopologyIndex
) -> dict[tuple[int, int], int]:
    capacity = pd.read_csv(source / HVDC_CAPACITY_FILE)
    cost = pd.read_csv(source / HVDC_COST_FILE)
    if len(capacity) != 1 or len(cost) != 1:
        raise ValueError(
            f"expected exactly 1 row in each of {HVDC_CAPACITY_FILE!r} and "
            f"{HVDC_COST_FILE!r}"
        )

    capacity_row = capacity.iloc[0]
    cost_row = cost.iloc[0]
    if (capacity_row["r"], capacity_row["rr"]) != (cost_row["r"], cost_row["rr"]):
        raise ValueError(
            f"{HVDC_CAPACITY_FILE} and {HVDC_COST_FILE}: (r, rr) pairs do not match"
        )

    start_bus = _bus_number(capacity_row["r"])
    end_bus = _bus_number(capacity_row["rr"])

    technology = NodalHVDCTransportTechnology(
        id=doc.next_id(),
        name=f"HVDC_{start_bus}_{end_bus}",
        available=True,
        power_systems_type="TwoTerminalGenericHVDCLine",
        start_node=inv_idx.node_id_by_bus_number[start_bus],
        end_node=inv_idx.node_id_by_bus_number[end_bus],
        capacity_limits=MinMax(min=0.0, max=float(capacity_row["MW"])),
        capital_costs=capital_costs_for(
            flat_linear_value_curve(float(cost_row["USD2004perMW"]))
        ),
        line_loss=None,
        financial_data=transport_financial_data(),
    )
    technology_id = doc.add_component(technology)
    return {(start_bus, end_bus): technology_id}


def add_transport_technologies(
    doc: PortfolioCase, source: Path, inv_idx: InvestmentTopologyIndex
) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], int]]:
    """Add every ``NodalACTransportTechnology`` (one per unique existing AC
    corridor, 108 total) and the one ``NodalHVDCTransportTechnology`` to
    ``doc``. Returns ``(ac_id_by_bus_pair, hvdc_id_by_bus_pair)``, each
    keyed by ``(start_bus_number, end_bus_number)``.
    """
    ac_id_by_bus_pair = _add_ac_transport_technologies(doc, source, inv_idx)
    hvdc_id_by_bus_pair = _add_hvdc_transport_technologies(doc, source, inv_idx)
    return ac_id_by_bus_pair, hvdc_id_by_bus_pair
