"""Investments policy-constraints stage: six illustrative policy component
types (R37) — ``CarbonCaps``, ``CarbonTax``, ``CapacityReserveMargin``,
``EnergyShareRequirements``, ``MinimumCapacityRequirements``,
``MaximumCapacityRequirements`` — wired to the ``SupplyTechnology``/
``StorageTechnology`` candidates they constrain.

**None of the values in this module come from ``RTS_inputs`` or any other
dataset file.** This is a worked policy scenario invented for this tutorial
so the capacity-expansion example has a realistic problem shape (an
80%-by-2050 carbon cap trajectory, a reserve margin inside the usual
10-15% band, an illustrative RPS-style energy share, and one min/max
capacity requirement each). A reader building a real case is expected to
replace every number here with their own policy design.

None of the six policy model classes carries a ``region`` or ``technology``
field of its own (confirmed against
``power_openapi_models.investments.models``), and neither does a technology
carry a list of the policies that bind it. The link is an *association
table*: ``PortfolioDocument.requirements_associations``, one
``RequirementAssociation`` row per (requirement, member) pair, exactly as
``service_associations`` links a reserve product to its contributing
generators. This module mints each policy component first, then records one
row per technology it targets via
``PortfolioCase.add_requirement_association``.

Earlier drafts of this tutorial instead pushed the policy id onto a
``requirements`` list on the technology itself. No release of SiennaSchemas
has ever defined that field — Python accepted it only because ``components``
is untyped, so the case built clean and produced documents that would fail
schema validation.

The scenario, verbatim from the task brief (not a judgment call — reuse
these exact numbers and targets when replacing this module):

- **``CarbonCaps`` x4** — one component per checkpoint year of an
  80%-by-2050 trajectory (2050's 1.6 Mt is 80% below 2025's 8.0 Mt).
  Targets: the 4 fossil-thermal ``SupplyTechnology`` candidates
  (``gas-cc``, ``gas-ct``, ``o-g-s``, ``coalolduns``) — the 5 other E2
  candidates (``nuclear``, ``hydED``, ``hydEND``, ``upv``, ``wind-ons``)
  don't burn carbon fuel and are excluded. ``max_tons_mwh`` is left at its
  schema default (only the absolute ``max_mtons`` form is set).
- **``CarbonTax`` x1** (2030, $15/ton) — same 4 fossil-thermal targets.
- **``CapacityReserveMargin`` x1** (2030, 13% of peak demand) — every
  ``SupplyTechnology`` (all 9) plus the 1 ``StorageTechnology``: everything
  that contributes firm/dispatchable capacity system-wide.
- **``EnergyShareRequirements`` x1** (2030, 30% generation share) — the 2
  renewable ``SupplyTechnology`` candidates, ``upv`` and ``wind-ons``.
- **``MinimumCapacityRequirements`` x1** (2035, 200 MW floor) — ``wind-ons``
  only, an RPS-like capacity floor.
- **``MaximumCapacityRequirements`` x1** (2035, 0 MW ceiling) — ``coalolduns``
  only, a coal-phase-out ceiling on *new candidate* capacity (this
  component type constrains the investable candidate, not existing units).
"""

from __future__ import annotations

from power_openapi_models.investments.models import (
    CapacityReserveMargin,
    CarbonCaps,
    CarbonTax,
    EnergyShareRequirements,
    MaximumCapacityRequirements,
    MinimumCapacityRequirements,
)

from rts_gmlc_case.document import PortfolioCase

# The 4 fossil-thermal SupplyTechnology candidate classes (E2's 9 minus
# nuclear/hydED/hydEND/upv/wind-ons, which don't burn carbon fuel).
FOSSIL_THERMAL_CLASSES = ("gas-cc", "gas-ct", "o-g-s", "coalolduns")

# The 2 renewable SupplyTechnology candidate classes.
RENEWABLE_CLASSES = ("upv", "wind-ons")

# (target_year, max_mtons) checkpoints of the 80%-by-2050 carbon cap
# trajectory. 1.6 is exactly 80% below 8.0.
CARBON_CAP_TRAJECTORY: tuple[tuple[int, float], ...] = (
    (2025, 8.0),
    (2030, 6.5),
    (2040, 3.5),
    (2050, 1.6),
)

CARBON_TAX_YEAR = 2030
CARBON_TAX_DOLLARS_PER_TON = 15.0

CAPACITY_RESERVE_MARGIN_YEAR = 2030
CAPACITY_RESERVE_FRACTION = 0.13

ENERGY_SHARE_YEAR = 2030
ENERGY_SHARE_FRACTION = 0.30

MINIMUM_CAPACITY_YEAR = 2035
MINIMUM_CAPACITY_MW = 200.0
MINIMUM_CAPACITY_CLASS = "wind-ons"

MAXIMUM_CAPACITY_YEAR = 2035
MAXIMUM_CAPACITY_MW = 0.0
MAXIMUM_CAPACITY_CLASS = "coalolduns"


def add_policy_constraints(
    doc: PortfolioCase,
    supply_ids: dict[str, int],
    storage_ids: dict[str, int],
) -> dict[str, list[int]]:
    """Add the 9 illustrative policy components described in this module's
    docstring, then wire each one's ``requirements`` targets via
    ``PortfolioCase.add_requirement_association``.

    ``supply_ids`` and ``storage_ids`` are ``add_supply_technologies``'s and
    ``add_storage_technologies``'s return values (class name -> minted id).
    Returns a mapping from policy-type name to the list of minted ids for
    that type (e.g. ``{"CarbonCaps": [id1, id2, id3, id4], ...}``).
    """
    minted: dict[str, list[int]] = {}

    carbon_cap_ids: list[int] = []
    for year, max_mtons in CARBON_CAP_TRAJECTORY:
        component_id = doc.add_component(
            CarbonCaps(
                id=doc.next_id(),
                name=f"Carbon cap {year}",
                available=True,
                target_year=year,
                max_mtons=max_mtons,
            )
        )
        carbon_cap_ids.append(component_id)
        for tech_class in FOSSIL_THERMAL_CLASSES:
            doc.add_requirement_association(
                requirement_id=component_id,
                entity_id=supply_ids[tech_class],
            )
    minted["CarbonCaps"] = carbon_cap_ids

    carbon_tax_id = doc.add_component(
        CarbonTax(
            id=doc.next_id(),
            name=f"Carbon tax {CARBON_TAX_YEAR}",
            available=True,
            target_year=CARBON_TAX_YEAR,
            tax_dollars_per_ton=CARBON_TAX_DOLLARS_PER_TON,
        )
    )
    for tech_class in FOSSIL_THERMAL_CLASSES:
        doc.add_requirement_association(
                requirement_id=carbon_tax_id,
                entity_id=supply_ids[tech_class],
            )
    minted["CarbonTax"] = [carbon_tax_id]

    reserve_margin_id = doc.add_component(
        CapacityReserveMargin(
            id=doc.next_id(),
            name=f"Capacity reserve margin {CAPACITY_RESERVE_MARGIN_YEAR}",
            available=True,
            target_year=CAPACITY_RESERVE_MARGIN_YEAR,
            capacity_reserve_fraction=CAPACITY_RESERVE_FRACTION,
        )
    )
    for tech_class in sorted(supply_ids):
        doc.add_requirement_association(
                requirement_id=reserve_margin_id,
                entity_id=supply_ids[tech_class],
            )
    for tech_class in sorted(storage_ids):
        doc.add_requirement_association(
                requirement_id=reserve_margin_id,
                entity_id=storage_ids[tech_class],
            )
    minted["CapacityReserveMargin"] = [reserve_margin_id]

    energy_share_id = doc.add_component(
        EnergyShareRequirements(
            id=doc.next_id(),
            name=f"RPS {ENERGY_SHARE_YEAR}",
            available=True,
            target_year=ENERGY_SHARE_YEAR,
            generation_fraction_requirement=ENERGY_SHARE_FRACTION,
        )
    )
    for tech_class in RENEWABLE_CLASSES:
        doc.add_requirement_association(
                requirement_id=energy_share_id,
                entity_id=supply_ids[tech_class],
            )
    minted["EnergyShareRequirements"] = [energy_share_id]

    minimum_capacity_id = doc.add_component(
        MinimumCapacityRequirements(
            id=doc.next_id(),
            name=f"Wind capacity floor {MINIMUM_CAPACITY_YEAR}",
            available=True,
            target_year=MINIMUM_CAPACITY_YEAR,
            min_capacity_mw=MINIMUM_CAPACITY_MW,
        )
    )
    doc.add_requirement_association(
                requirement_id=minimum_capacity_id,
                entity_id=supply_ids[MINIMUM_CAPACITY_CLASS],
            )
    minted["MinimumCapacityRequirements"] = [minimum_capacity_id]

    maximum_capacity_id = doc.add_component(
        MaximumCapacityRequirements(
            id=doc.next_id(),
            name=f"Coal phase-out {MAXIMUM_CAPACITY_YEAR}",
            available=True,
            target_year=MAXIMUM_CAPACITY_YEAR,
            max_capacity_mw=MAXIMUM_CAPACITY_MW,
        )
    )
    doc.add_requirement_association(
                requirement_id=maximum_capacity_id,
                entity_id=supply_ids[MAXIMUM_CAPACITY_CLASS],
            )
    minted["MaximumCapacityRequirements"] = [maximum_capacity_id]

    return minted
