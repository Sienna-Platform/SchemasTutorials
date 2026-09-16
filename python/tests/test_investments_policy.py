import warnings

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.policy import (
    CAPACITY_RESERVE_FRACTION,
    CAPACITY_RESERVE_MARGIN_YEAR,
    CARBON_CAP_TRAJECTORY,
    CARBON_TAX_DOLLARS_PER_TON,
    CARBON_TAX_YEAR,
    ENERGY_SHARE_FRACTION,
    ENERGY_SHARE_YEAR,
    FOSSIL_THERMAL_CLASSES,
    MAXIMUM_CAPACITY_CLASS,
    MAXIMUM_CAPACITY_MW,
    MAXIMUM_CAPACITY_YEAR,
    MINIMUM_CAPACITY_CLASS,
    MINIMUM_CAPACITY_MW,
    MINIMUM_CAPACITY_YEAR,
    RENEWABLE_CLASSES,
    add_policy_constraints,
)
from rts_gmlc_case.investments.storage import add_storage_technologies
from rts_gmlc_case.investments.technologies import add_supply_technologies
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.topology import add_topology

# The order add_policy_constraints processes the 6 policy types in --
# reused here to build each technology's *expected* requirements list in
# the same order the production code appends to it.
POLICY_TYPES_IN_PROCESSING_ORDER = (
    "CarbonCaps",
    "CarbonTax",
    "CapacityReserveMargin",
    "EnergyShareRequirements",
    "MinimumCapacityRequirements",
    "MaximumCapacityRequirements",
)


def _build():
    """Build the operations stages, then E1-E4's investments stages, then
    this task's policy stage on top -- this task needs both E2's and E3's
    outputs, so the fixture runs the whole chain rather than just
    `investments.policy` in isolation.

    Returns the `(system, portfolio)` pair plus the stage outputs: policy
    components live in the portfolio, the generators they are checked
    against live in the system.
    """
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    add_generation(doc, op_src, idx)

    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    supply_ids = add_supply_technologies(portfolio, inv_src, idx, inv_idx)
    storage_ids = add_storage_technologies(portfolio, inv_src, inv_idx)
    minted = add_policy_constraints(portfolio, supply_ids, storage_ids)
    return doc, portfolio, supply_ids, storage_ids, minted


def _scenario_targets(supply_ids: dict[str, int], storage_ids: dict[str, int]):
    """The scenario table from `investments/policy.py`'s docstring,
    expressed as {policy_type_name: set_of_target_class_names} --
    the same declarative shape the module builds from, not a re-typed
    per-class magic-number table.
    """
    return {
        "CarbonCaps": set(FOSSIL_THERMAL_CLASSES),
        "CarbonTax": set(FOSSIL_THERMAL_CLASSES),
        "CapacityReserveMargin": set(supply_ids) | set(storage_ids),
        "EnergyShareRequirements": set(RENEWABLE_CLASSES),
        "MinimumCapacityRequirements": {MINIMUM_CAPACITY_CLASS},
        "MaximumCapacityRequirements": {MAXIMUM_CAPACITY_CLASS},
    }


def _expected_requirements(
    class_name: str,
    targets_by_policy: dict[str, set[str]],
    minted: dict[str, list[int]],
) -> list[int]:
    """The exact, ordered list of policy ids `class_name` should end up
    bound to: for each policy type in production-processing order, append
    that type's minted id(s) if `class_name` is one of its targets.
    """
    expected: list[int] = []
    for policy_type in POLICY_TYPES_IN_PROCESSING_ORDER:
        if class_name in targets_by_policy[policy_type]:
            expected.extend(minted[policy_type])
    return expected


def test_exactly_9_policy_components_4_carbon_caps_plus_1_each_of_5_others():
    doc, portfolio, *_ = _build()

    assert len(portfolio.document.components["CarbonCaps"]) == 4
    for type_name in (
        "CarbonTax",
        "CapacityReserveMargin",
        "EnergyShareRequirements",
        "MinimumCapacityRequirements",
        "MaximumCapacityRequirements",
    ):
        assert len(portfolio.document.components[type_name]) == 1

    total = len(portfolio.document.components["CarbonCaps"]) + sum(
        len(portfolio.document.components[type_name])
        for type_name in (
            "CarbonTax",
            "CapacityReserveMargin",
            "EnergyShareRequirements",
            "MinimumCapacityRequirements",
            "MaximumCapacityRequirements",
        )
    )
    assert total == 9


def test_add_policy_constraints_return_value_matches_component_counts():
    doc, portfolio, supply_ids, storage_ids, minted = _build()

    assert set(minted) == set(POLICY_TYPES_IN_PROCESSING_ORDER)
    assert len(minted["CarbonCaps"]) == 4
    for type_name in POLICY_TYPES_IN_PROCESSING_ORDER:
        if type_name != "CarbonCaps":
            assert len(minted[type_name]) == 1
        for component_id in minted[type_name]:
            assert any(
                item["id"] == component_id for item in portfolio.document.components[type_name]
            )


def test_carbon_caps_trajectory_values_match_the_scenario_table():
    doc, portfolio, *_ = _build()

    caps_by_year = {cap["target_year"]: cap for cap in portfolio.document.components["CarbonCaps"]}
    assert set(caps_by_year) == {year for year, _ in CARBON_CAP_TRAJECTORY}
    for year, max_mtons in CARBON_CAP_TRAJECTORY:
        cap = caps_by_year[year]
        assert cap["max_mtons"] == max_mtons
        assert cap["available"] is True

    # 80%-by-2050 relative to the 2025 figure.
    cap_2025 = caps_by_year[2025]["max_mtons"]
    cap_2050 = caps_by_year[2050]["max_mtons"]
    assert cap_2050 == cap_2025 * 0.2


def test_carbon_tax_capacity_reserve_margin_and_energy_share_values():
    doc, portfolio, *_ = _build()

    tax = portfolio.document.components["CarbonTax"][0]
    assert tax["target_year"] == CARBON_TAX_YEAR
    assert tax["tax_dollars_per_ton"] == CARBON_TAX_DOLLARS_PER_TON

    reserve_margin = portfolio.document.components["CapacityReserveMargin"][0]
    assert reserve_margin["target_year"] == CAPACITY_RESERVE_MARGIN_YEAR
    assert reserve_margin["capacity_reserve_fraction"] == CAPACITY_RESERVE_FRACTION
    assert 0.10 <= reserve_margin["capacity_reserve_fraction"] <= 0.15

    energy_share = portfolio.document.components["EnergyShareRequirements"][0]
    assert energy_share["target_year"] == ENERGY_SHARE_YEAR
    assert energy_share["generation_fraction_requirement"] == ENERGY_SHARE_FRACTION


def test_minimum_and_maximum_capacity_requirement_values():
    doc, portfolio, *_ = _build()

    minimum = portfolio.document.components["MinimumCapacityRequirements"][0]
    assert minimum["target_year"] == MINIMUM_CAPACITY_YEAR
    assert minimum["min_capacity_mw"] == MINIMUM_CAPACITY_MW

    maximum = portfolio.document.components["MaximumCapacityRequirements"][0]
    assert maximum["target_year"] == MAXIMUM_CAPACITY_YEAR
    assert maximum["max_capacity_mw"] == MAXIMUM_CAPACITY_MW


def test_every_supply_and_storage_technology_is_bound_to_exactly_the_expected_policies():
    doc, portfolio, supply_ids, storage_ids, minted = _build()
    targets_by_policy = _scenario_targets(supply_ids, storage_ids)

    bound_by_entity: dict[int, list[int]] = {}
    for row in portfolio.document.requirements_associations:
        bound_by_entity.setdefault(row.entity_id, []).append(row.requirement_id)

    for type_name in ("SupplyTechnology", "StorageTechnology"):
        for tech in portfolio.document.components[type_name]:
            expected = _expected_requirements(tech["name"], targets_by_policy, minted)
            actual = bound_by_entity.get(tech["id"], [])
            assert actual == expected, (
                f"{tech['name']}: bound to {actual} != expected {expected}"
            )


def test_no_technology_component_carries_a_requirements_key():
    """The membership lives in `requirements_associations`, never on the
    component. `components` is untyped, so nothing but this test stops a
    stray key from riding along into a document that would fail schema
    validation.
    """
    doc, portfolio, *_ = _build()

    for type_name in ("SupplyTechnology", "StorageTechnology"):
        for tech in portfolio.document.components[type_name]:
            assert "requirements" not in tech


def test_every_association_resolves_to_a_real_component_id():
    doc, portfolio, *_ = _build()

    all_ids = {
        item["id"]
        for items in list(portfolio.document.components.values())
        + list(doc.document.components.values())
        for item in items
    }

    assert portfolio.document.requirements_associations
    for row in portfolio.document.requirements_associations:
        assert row.requirement_id in all_ids
        assert row.entity_id in all_ids


def test_validate_passes():
    doc, portfolio, *_ = _build()
    doc.validate()
    portfolio.validate()


def test_no_warnings_building_policy_constraints():
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    add_generation(doc, op_src, idx)
    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    supply_ids = add_supply_technologies(portfolio, inv_src, idx, inv_idx)
    storage_ids = add_storage_technologies(portfolio, inv_src, inv_idx)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        add_policy_constraints(portfolio, supply_ids, storage_ids)
