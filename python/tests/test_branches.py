import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.branches import add_branches
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import add_topology


def test_branch_partition_and_arcs():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    add_branches(doc, src, idx)

    br = pd.read_csv(src / "branch.csv")
    dc = pd.read_csv(src / "dc_branch.csv")
    bus = pd.read_csv(src / "bus.csv")
    base_kv = dict(zip(bus["Bus ID"], bus["BaseKV"]))

    # Two independent classification rules must agree exactly (R21).
    tr_ratio_rule = ~br["Tr Ratio"].isin([0.0, 1.0])
    voltage_rule = br.apply(
        lambda row: base_kv[row["From Bus"]] != base_kv[row["To Bus"]], axis=1
    )
    assert (tr_ratio_rule == voltage_rule).all()
    n_xf = int(tr_ratio_rule.sum())

    assert len(doc.document.components["Line"]) == len(br) - n_xf
    assert len(doc.document.components["TwoWindingTransformer"]) == n_xf
    assert len(doc.document.components["TransformerCircuit"]) == n_xf

    # Pinned expected totals (CAMPAIGN-FACTS.md "Expected component counts", R21).
    assert len(doc.document.components["Line"]) == 105
    assert len(doc.document.components["TransformerCircuit"]) == 15
    assert len(doc.document.components["TwoWindingTransformer"]) == 15
    assert len(doc.document.components["TwoTerminalGenericHVDCLine"]) == 1

    pairs = [(a["from_id"], a["to_id"]) for a in doc.document.components["Arc"]]
    assert len(set(pairs)) == len(pairs)  # deduplicated

    ac_pairs = {
        (idx.bus_id_by_number[int(row["From Bus"])], idx.bus_id_by_number[int(row["To Bus"])])
        for row in br.to_dict("records")
    }
    dc_pairs = {
        (idx.bus_id_by_number[int(row["From Bus"])], idx.bus_id_by_number[int(row["To Bus"])])
        for row in dc.to_dict("records")
    }
    assert len(ac_pairs) == 108
    assert len(dc_pairs) == 1
    assert len(ac_pairs | dc_pairs) == len(doc.document.components["Arc"])
    assert len(doc.document.components["Arc"]) == 109

    # No transformer circuit's name field (it has none) and no line is missing an arc.
    for line in doc.document.components["Line"]:
        assert line["arc"] in {a["id"] for a in doc.document.components["Arc"]}
    for circuit in doc.document.components["TransformerCircuit"]:
        assert "name" not in circuit
    xf_names = {t["name"] for t in doc.document.components["TwoWindingTransformer"]}
    xf_uids = set(br.loc[tr_ratio_rule, "UID"])
    assert xf_names == xf_uids

    hvdc = doc.document.components["TwoTerminalGenericHVDCLine"][0]
    assert hvdc["name"] == "DC1"
    assert hvdc["active_power_limits_from"] == {"min": -100.0, "max": 100.0}
    assert hvdc["active_power_limits_to"] == {"min": -100.0, "max": 100.0}
    assert hvdc["reactive_power_limits_from"] == {"min": 0.0, "max": 100.0}
    assert hvdc["reactive_power_limits_to"] == {"min": 0.0, "max": 100.0}
    assert hvdc["loss"]["value_curve"]["function_data"]["proportional_term"] == 0.1

    doc.validate()


def test_line_a1_spot_check():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    add_branches(doc, src, idx)

    a1 = next(c for c in doc.document.components["Line"] if c["name"] == "A1")
    assert a1["r"] == 0.003
    assert a1["x"] == 0.014
    assert a1["b"]["from"] == 0.2305
    assert a1["b"]["to"] == 0.2305
    assert a1["rating"] == 175.0
    assert a1["rating_b"] == 193.0
    assert a1["rating_c"] == 200.0
    assert a1["base_power"] == 100.0
    assert a1["power_units"] == "NATURAL_UNITS"
    assert a1["parameter_units"] == "COMPONENT_BASE"
    assert a1["angle_limits"] == {"min": -3.1416, "max": 3.1416}
