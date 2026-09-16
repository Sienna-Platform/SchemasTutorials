import math
import warnings

import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.storage import BATTERY_TECH_CLASS, add_storage_technologies
from rts_gmlc_case.investments.technologies import GENERATOR_DATABASE, add_supply_technologies
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.topology import add_topology


def _build(doc: CaseDocument):
    """Build the operations stages (topology + generation, fast: no
    time-series read) plus the investments topology and supply-technology
    stages, then run the storage-technology stage on top -- mirrors
    test_investments_technologies.py's ``_build`` helper.
    """
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    add_generation(doc, op_src, idx)

    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    add_supply_technologies(portfolio, inv_src, idx, inv_idx)
    storage_id_by_class = add_storage_technologies(portfolio, inv_src, inv_idx)
    return portfolio, idx, inv_idx, storage_id_by_class


def _battery_row() -> pd.Series:
    gen_db = pd.read_csv(investments_data.investments_source_dir() / GENERATOR_DATABASE)
    rows = gen_db[gen_db["tech"] == BATTERY_TECH_CLASS]
    assert len(rows) == 1
    return rows.iloc[0]


def test_exactly_one_battery_4_row_in_the_generator_database():
    row = _battery_row()
    assert row["GEN UID"] == "313_STORAGE_1"
    assert int(row["Bus ID"]) == 313
    assert float(row["cap"]) == 50.0
    assert float(row["Storage Roundtrip Efficiency"]) == 85.0


def test_both_duration_csvs_have_zero_data_rows():
    # R37: duration_limits is left None on the StorageTechnology because
    # neither duration source has any real data -- this pins that fact
    # against a fresh read so a future dataset refresh that adds rows is
    # caught, not silently left with a stale None.
    source = investments_data.investments_source_dir()
    pshdata = pd.read_csv(source / "storagedata/storage_duration_pshdata.csv")
    storinmaxfrac = pd.read_csv(source / "storagedata/storinmaxfrac.csv")
    assert len(pshdata) == 0
    assert len(storinmaxfrac) == 0


def test_exactly_one_storage_technology_named_battery_4():
    doc = CaseDocument()
    portfolio, idx, inv_idx, storage_id_by_class = _build(doc)

    assert len(portfolio.document.components["StorageTechnology"]) == 1
    assert set(storage_id_by_class) == {BATTERY_TECH_CLASS}

    tech = portfolio.document.components["StorageTechnology"][0]
    assert tech["name"] == BATTERY_TECH_CLASS
    assert tech["id"] == storage_id_by_class[BATTERY_TECH_CLASS]


def test_power_systems_type_is_energy_reservoir_storage_and_present_in_document():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    assert tech["power_systems_type"] == "EnergyReservoirStorage"
    # R39's 4th string, not produced by any of E2's 9 SupplyTechnology
    # classes -- confirmed present with at least one real component here.
    assert tech["power_systems_type"] in doc.document.components
    assert len(doc.document.components[tech["power_systems_type"]]) > 0

    supply_types = {
        supply["power_systems_type"] for supply in portfolio.document.components["SupplyTechnology"]
    }
    assert "EnergyReservoirStorage" not in supply_types


def test_region_is_the_zone_containing_bus_313():
    doc = CaseDocument()
    portfolio, idx, inv_idx, storage_id_by_class = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    expected_zone_id = inv_idx.zone_id_by_bus_number[313]
    assert tech["region"] == [expected_zone_id]


def test_efficiency_reuses_the_generation_module_formula():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    row = _battery_row()
    expected_leg = math.sqrt(float(row["Storage Roundtrip Efficiency"]) / 100.0)
    assert tech["efficiency"]["in"] == expected_leg
    assert tech["efficiency"]["out"] == expected_leg


def test_storage_tech_and_prime_mover_type():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    assert tech["storage_tech"] == "OTHER_CHEM"
    assert tech["prime_mover_type"] == "BA"


def test_capacity_limits_use_cap_mw_for_power_not_energy():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    row = _battery_row()
    cap_mw = float(row["cap"])
    assert tech["capacity_limits_charge"] == {"min": 0.0, "max": cap_mw}
    assert tech["capacity_limits_discharge"] == {"min": 0.0, "max": cap_mw}
    # cap is a power (MW) figure -- no dataset-backed energy (MWh) capacity
    # figure exists, so capacity_limits_energy is left None, not fabricated.
    assert tech["capacity_limits_energy"] is None


def test_duration_limits_is_none():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]
    assert tech["duration_limits"] is None


def test_existing_devices_attribute():
    doc = CaseDocument()
    portfolio, idx, inv_idx, storage_id_by_class = _build(doc)

    technology_id = storage_id_by_class[BATTERY_TECH_CLASS]
    existing_devices_by_component_id = {
        assoc.component_id: portfolio.document.supplemental_attributes[i]
        for i, assoc in enumerate(portfolio.document.supplemental_attribute_associations)
        if assoc.attribute_type == "ExistingDevices" and assoc.component_type == "StorageTechnology"
    }
    assert len(existing_devices_by_component_id) == 1
    assert existing_devices_by_component_id[technology_id]["existing_devices"] == [
        "313_STORAGE_1"
    ]


def test_capital_costs_operation_cost_and_financial_data_populated():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    tech = portfolio.document.components["StorageTechnology"][0]

    # The three legs travel in one StorageCapitalCost, not as sibling fields.
    assert tech["capital_costs"]["charge_capital_cost"] is not None
    assert tech["capital_costs"]["discharge_capital_cost"] is not None
    assert tech["capital_costs"]["energy_capital_cost"] is not None
    assert tech["operation_costs"] is not None
    assert tech["financial_data"] is not None
    for field in (
        "capital_recovery_period",
        "technology_base_year",
        "debt_fraction",
        "debt_rate",
        "return_on_equity",
        "tax_rate",
    ):
        assert tech["financial_data"][field] is not None


def test_validate_passes():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    doc.validate()


def test_no_warnings_building_storage_technologies():
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    add_generation(doc, op_src, idx)
    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    add_supply_technologies(portfolio, inv_src, idx, inv_idx)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        add_storage_technologies(portfolio, inv_src, inv_idx)
