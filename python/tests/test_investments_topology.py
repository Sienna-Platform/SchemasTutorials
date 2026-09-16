"""The investments topology stage adds nothing to the document.

SiennaSchemas 0.1.0 defines no `Node` and no `Zone`, so all the stage can do is
hand back the operations ids later stages point their `region` fields at. These
tests assert exactly that: the portfolio stays empty, and every id in the
returned index resolves to an `ACBus` or `Area` in the base system.
"""

import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.topology import add_topology


def _build():
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)
    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)
    return doc, portfolio, idx, inv_idx


def test_investment_topology_adds_nothing_to_the_document():
    doc, portfolio, idx, inv_idx = _build()

    # No Node, no Zone, and no TopologyMapping: the schema has no investments
    # topology component, and the bus/area membership is already on ACBus.area.
    assert portfolio.document.components == {}
    assert portfolio.document.supplemental_attributes == []
    assert portfolio.document.supplemental_attribute_associations == []

    doc.validate()
    portfolio.validate()


def test_zone_membership_is_readable_from_acbus_area_alone():
    """What the dropped TopologyMapping would have restated: every bus already
    names its zone, in the base system, via `ACBus.area`.
    """
    doc, portfolio, idx, inv_idx = _build()

    for bus in doc.document.components["ACBus"]:
        assert inv_idx.zone_id_by_bus_number[bus["number"]] == bus["area"]


def test_node_ids_are_the_operations_acbus_ids():
    doc, portfolio, idx, inv_idx = _build()
    bus = pd.read_csv(data.rts_source_dir() / "SourceData" / "bus.csv")

    assert inv_idx.node_id_by_bus_number == idx.bus_id_by_number
    assert set(inv_idx.node_id_by_bus_number) == set(bus["Bus ID"].tolist())
    assert len(inv_idx.node_id_by_bus_number) == 73

    acbus_by_id = {c["id"]: c for c in doc.document.components["ACBus"]}
    abel = acbus_by_id[inv_idx.node_id_by_bus_number[101]]
    assert abel["name"] == "Abel"
    assert abel["bustype"] == "PV"


def test_zones_are_the_3_rts_areas_not_the_5_reeds_bas():
    doc, portfolio, idx, inv_idx = _build()

    assert inv_idx.zone_id_by_name == idx.area_id_by_name
    assert set(inv_idx.zone_id_by_name) == {"1", "2", "3"}

    area_names = {a["name"] for a in doc.document.components["Area"]}
    assert area_names == {"1", "2", "3"}

    hierarchy = pd.read_csv(investments_data.investments_source_dir() / "hierarchy_rts.csv")
    ba_codes = set(hierarchy["ba"].unique())
    assert len(ba_codes) == 5
    assert set(inv_idx.zone_id_by_name).isdisjoint(ba_codes)


def test_zone_id_by_bus_number_maps_every_bus_to_its_area():
    doc, portfolio, idx, inv_idx = _build()
    bus = pd.read_csv(data.rts_source_dir() / "SourceData" / "bus.csv")

    assert set(inv_idx.zone_id_by_bus_number) == set(bus["Bus ID"].tolist())
    for row in bus.to_dict("records"):
        expected = idx.area_id_by_name[str(int(row["Area"]))]
        assert inv_idx.zone_id_by_bus_number[int(row["Bus ID"])] == expected
