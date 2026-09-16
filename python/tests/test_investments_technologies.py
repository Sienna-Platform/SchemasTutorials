import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.technologies import (
    GENERATOR_DATABASE,
    POWER_SYSTEMS_TYPE_BY_CLASS,
    add_supply_technologies,
)
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.topology import add_topology

EXCLUDED_CLASSES = {"distpv", "csp-ns", "battery_4"}

R39_POWER_SYSTEMS_TYPES = {
    "ThermalStandard",
    "RenewableDispatch",
    "HydroDispatch",
    "EnergyReservoirStorage",
}


def _build(doc: CaseDocument):
    """Build the operations stages this test needs (topology + generation,
    fast: no time-series read, not `slow`) so the operations component
    types (``ThermalStandard``/``HydroDispatch``/``RenewableDispatch``) are
    already present in the document, then run the investments topology and
    supply-technology stages on top.
    """
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    add_generation(doc, op_src, idx)

    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    tech_id_by_class = add_supply_technologies(portfolio, inv_src, idx, inv_idx)
    return portfolio, idx, inv_idx, tech_id_by_class


def _generator_database() -> pd.DataFrame:
    return pd.read_csv(investments_data.investments_source_dir() / GENERATOR_DATABASE)


def test_every_row_is_an_existing_unit():
    gen_db = _generator_database()
    assert len(gen_db) == 155
    assert gen_db["IsExistUnit"].all()


def test_exactly_9_supply_technologies_named_by_the_9_classes():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    assert len(portfolio.document.components["SupplyTechnology"]) == 9
    assert set(tech_id_by_class) == set(POWER_SYSTEMS_TYPE_BY_CLASS) == {
        "gas-cc",
        "gas-ct",
        "o-g-s",
        "coalolduns",
        "nuclear",
        "hydED",
        "hydEND",
        "upv",
        "wind-ons",
    }
    assert set(tech_id_by_class).isdisjoint(EXCLUDED_CLASSES)

    gen_db = _generator_database()
    assert EXCLUDED_CLASSES <= set(gen_db["tech"].unique())

    names = {c["name"] for c in portfolio.document.components["SupplyTechnology"]}
    assert names == set(tech_id_by_class)


def test_power_systems_type_is_an_r39_string_present_in_the_document():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    assert set(POWER_SYSTEMS_TYPE_BY_CLASS.values()) <= R39_POWER_SYSTEMS_TYPES

    for tech in portfolio.document.components["SupplyTechnology"]:
        expected = POWER_SYSTEMS_TYPE_BY_CLASS[tech["name"]]
        assert tech["power_systems_type"] == expected
        # The type actually has at least one component under it in this
        # same document (built from the operations stages above) -- not a
        # deferred check.
        assert tech["power_systems_type"] in doc.document.components
        assert len(doc.document.components[tech["power_systems_type"]]) > 0


def test_existing_devices_counts_match_the_generator_database():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)
    gen_db = _generator_database()

    existing_devices_by_technology_id = {
        assoc.component_id: portfolio.document.supplemental_attributes[i]
        for i, assoc in enumerate(portfolio.document.supplemental_attribute_associations)
        if assoc.attribute_type == "ExistingDevices"
    }
    assert len(existing_devices_by_technology_id) == 9

    for tech_class, technology_id in tech_id_by_class.items():
        expected_uids = sorted(
            str(uid) for uid in gen_db.loc[gen_db["tech"] == tech_class, "GEN UID"]
        )
        attribute = existing_devices_by_technology_id[technology_id]
        assert attribute["existing_devices"] == expected_uids
        assert len(attribute["existing_devices"]) == (gen_db["tech"] == tech_class).sum()

    # Pinned counts from the brief's table.
    assert (gen_db["tech"] == "gas-ct").sum() == 27
    assert (gen_db["tech"] == "hydED").sum() == 19
    assert (gen_db["tech"] == "o-g-s").sum() == 19


def test_supplemental_attribute_associations_point_at_supply_technology():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    technology_ids = set(tech_id_by_class.values())
    associations = [
        assoc
        for assoc in portfolio.document.supplemental_attribute_associations
        if assoc.attribute_type == "ExistingDevices"
    ]
    assert len(associations) == 9
    for assoc in associations:
        assert assoc.component_type == "SupplyTechnology"
        assert assoc.component_id in technology_ids


def test_region_resolves_to_real_zone_ids():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    zone_ids = set(inv_idx.zone_id_by_name.values())
    assert zone_ids  # sanity: E1 produced at least one zone

    for tech in portfolio.document.components["SupplyTechnology"]:
        assert tech["region"], f"{tech['name']}: region must be non-empty"
        assert set(tech["region"]) <= zone_ids
        assert tech["region"] == sorted(tech["region"])

    doc.validate()


def test_fuel_only_set_for_thermal_classes():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    thermal_classes = {"gas-cc", "gas-ct", "o-g-s", "coalolduns", "nuclear"}
    for tech in portfolio.document.components["SupplyTechnology"]:
        if tech["name"] in thermal_classes:
            assert tech["fuel"] is not None
            assert len(tech["fuel"]) == 1
        else:
            assert tech["fuel"] is None


def test_financial_data_fully_populated():
    doc = CaseDocument()
    portfolio, idx, inv_idx, tech_id_by_class = _build(doc)

    required_fields = {
        "capital_recovery_period",
        "technology_base_year",
        "debt_fraction",
        "debt_rate",
        "return_on_equity",
        "tax_rate",
    }
    for tech in portfolio.document.components["SupplyTechnology"]:
        financial_data = tech["financial_data"]
        assert financial_data is not None
        for field in required_fields:
            assert financial_data.get(field) is not None, (
                f"{tech['name']}: financial_data.{field} is None"
            )
        assert tech["capital_costs"] is not None


def test_validate_passes():
    doc = CaseDocument()
    _build(doc)
    doc.validate()
