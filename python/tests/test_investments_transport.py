import warnings

import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.investments.transport import (
    AC_CAPACITY_FILE,
    AC_COST_FILE,
    HVDC_CAPACITY_FILE,
    HVDC_COST_FILE,
    add_transport_technologies,
)
from rts_gmlc_case.topology import add_topology


def _build(doc: CaseDocument):
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    ac_id_by_bus_pair, hvdc_id_by_bus_pair = add_transport_technologies(portfolio, inv_src, inv_idx)
    return portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair


def _source():
    return investments_data.investments_source_dir()


def test_ac_capacity_file_has_120_rows_and_108_unique_bus_pairs_with_12_exact_duplicates():
    capacity = pd.read_csv(_source() / AC_CAPACITY_FILE)
    assert len(capacity) == 120

    grouped = capacity.groupby(["From_Bus", "To_Bus"])
    assert grouped.ngroups == 108

    duplicate_sizes = grouped.size()
    duplicates = duplicate_sizes[duplicate_sizes > 1]
    assert len(duplicates) == 12

    # Every duplicate pair's rows are exactly identical (same MW_f0/MW_r0).
    for (from_bus, to_bus), _ in duplicates.items():
        rows = capacity[(capacity["From_Bus"] == from_bus) & (capacity["To_Bus"] == to_bus)]
        assert rows["MW_f0"].nunique() == 1
        assert rows["MW_r0"].nunique() == 1

    assert (capacity["MW_f0"] == capacity["MW_r0"]).all()


def test_ac_cost_file_has_108_rows_matching_the_capacity_files_unique_pairs():
    capacity = pd.read_csv(_source() / AC_CAPACITY_FILE)
    cost = pd.read_csv(_source() / AC_COST_FILE)
    assert len(cost) == 108
    assert not cost.duplicated(subset=["r", "rr"]).any()

    capacity_pairs = set(zip(capacity["From_Bus"], capacity["To_Bus"]))
    cost_pairs = set(zip(cost["r"], cost["rr"]))
    assert capacity_pairs == cost_pairs


def test_hvdc_files_have_exactly_one_matching_row():
    capacity = pd.read_csv(_source() / HVDC_CAPACITY_FILE)
    cost = pd.read_csv(_source() / HVDC_COST_FILE)
    assert len(capacity) == 1
    assert len(cost) == 1
    assert (capacity.iloc[0]["r"], capacity.iloc[0]["rr"]) == ("b113", "b316")
    assert (cost.iloc[0]["r"], cost.iloc[0]["rr"]) == ("b113", "b316")
    assert float(capacity.iloc[0]["MW"]) == 100.0


def test_nodal_ac_transport_technology_count_matches_a_fresh_csv_read():
    doc = CaseDocument()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build(doc)

    capacity = pd.read_csv(_source() / AC_CAPACITY_FILE)
    expected_pair_count = capacity.groupby(["From_Bus", "To_Bus"]).ngroups

    assert len(portfolio.document.components["NodalACTransportTechnology"]) == expected_pair_count
    assert len(ac_id_by_bus_pair) == expected_pair_count
    # Load-bearing for Task E6's cross-language check.
    assert expected_pair_count == 108


def test_duplicate_pair_capacity_is_summed():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)

    # b115/b121 is one of the 12 duplicated pairs, MW_f0=500 on each of its
    # two rows -- the resulting NodalACTransportTechnology's capacity must
    # be the sum, 1000, not a single row's 500.
    technologies = {
        tech["name"]: tech for tech in portfolio.document.components["NodalACTransportTechnology"]
    }
    assert technologies["AC_115_121"]["capacity_limits"]["max"] == 1000.0

    # A non-duplicated pair keeps its single-row value unchanged.
    assert technologies["AC_101_102"]["capacity_limits"]["max"] == 175.0


def test_every_ac_and_hvdc_start_end_node_resolves_to_a_real_node_id():
    doc = CaseDocument()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build(doc)

    # A "node" is an operations ACBus: the schema has no investments Node.
    node_ids = {bus["id"] for bus in doc.document.components["ACBus"]}
    assert node_ids == set(inv_idx.node_id_by_bus_number.values())

    for tech in portfolio.document.components["NodalACTransportTechnology"]:
        assert tech["start_node"] in node_ids
        assert tech["end_node"] in node_ids

    for tech in portfolio.document.components["NodalHVDCTransportTechnology"]:
        assert tech["start_node"] in node_ids
        assert tech["end_node"] in node_ids


def test_exactly_one_hvdc_transport_technology_with_capacity_100():
    doc = CaseDocument()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build(doc)

    assert len(portfolio.document.components["NodalHVDCTransportTechnology"]) == 1
    assert len(hvdc_id_by_bus_pair) == 1
    tech = portfolio.document.components["NodalHVDCTransportTechnology"][0]
    assert tech["capacity_limits"]["max"] == 100.0
    assert tech["line_loss"] is None

    expected_start = inv_idx.node_id_by_bus_number[113]
    expected_end = inv_idx.node_id_by_bus_number[316]
    assert tech["start_node"] == expected_start
    assert tech["end_node"] == expected_end


def test_ac_capital_costs_are_dataset_sourced_not_illustrative():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)

    cost = pd.read_csv(_source() / AC_COST_FILE)
    cost_by_pair = {
        (row["r"], row["rr"]): float(row["USD2004perMW"]) for row in cost.to_dict("records")
    }

    technologies = portfolio.document.components["NodalACTransportTechnology"]
    assert len(technologies) == len(cost_by_pair)
    for tech in technologies:
        _, from_bus, to_bus = tech["name"].split("_")
        expected_cost = cost_by_pair[(f"b{from_bus}", f"b{to_bus}")]
        curve = tech["capital_costs"]["capital_cost"]["function_data"]
        assert curve["proportional_term"] == expected_cost
        assert curve["constant_term"] == 0.0


def test_hvdc_capital_cost_matches_the_dc_cost_file():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)

    cost = pd.read_csv(_source() / HVDC_COST_FILE)
    expected_cost = float(cost.iloc[0]["USD2004perMW"])

    tech = portfolio.document.components["NodalHVDCTransportTechnology"][0]
    curve = tech["capital_costs"]["capital_cost"]["function_data"]
    assert curve["proportional_term"] == expected_cost


def test_every_transport_financial_data_has_capital_recovery_period_40():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)

    for tech in portfolio.document.components["NodalACTransportTechnology"]:
        assert tech["financial_data"]["capital_recovery_period"] == 40
    for tech in portfolio.document.components["NodalHVDCTransportTechnology"]:
        assert tech["financial_data"]["capital_recovery_period"] == 40


def test_resistance_reactance_voltage_unit_size_left_at_schema_defaults():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)

    for tech in portfolio.document.components["NodalACTransportTechnology"]:
        assert tech["resistance"] == 0.0
        assert tech["reactance"] == 0.0
        assert tech["voltage"] == 0.0
        assert tech["unit_size"] == 0.0


def test_validate_passes():
    doc = CaseDocument()
    portfolio, *_ = _build(doc)
    doc.validate()


def test_no_warnings_building_transport_technologies():
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        add_transport_technologies(portfolio, inv_src, inv_idx)
