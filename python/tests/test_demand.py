import pandas as pd
import pytest

from rts_gmlc_case import data
from rts_gmlc_case.demand import add_loads, add_reserves
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.topology import add_topology


def _parse_tuple_field(raw: str) -> list[str]:
    text = str(raw).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return [item.strip() for item in text.split(",") if item.strip()]


def _built_case():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    gen_ids = add_generation(doc, src, idx)
    add_loads(doc, src, idx)
    reserve_ids = add_reserves(doc, src, idx, gen_ids)
    return doc, src, reserve_ids


def test_loads_one_per_nonzero_bus():
    doc, src, _ = _built_case()
    bus = pd.read_csv(src / "bus.csv")
    expected = int((bus["MW Load"] != 0).sum())

    assert expected == 51
    assert len(doc.document.components["PowerLoad"]) == expected

    doc.validate()


def test_load_fields_match_reference_row_101():
    doc, src, _ = _built_case()
    bus = pd.read_csv(src / "bus.csv")
    row = bus[bus["Bus ID"] == 101].iloc[0]

    load = next(
        c for c in doc.document.components["PowerLoad"] if c["name"] == row["Bus Name"]
    )
    assert load["active_power"] == float(row["MW Load"])
    assert load["max_active_power"] == float(row["MW Load"])
    assert load["reactive_power"] == float(row["MVAR Load"])
    assert load["max_reactive_power"] == float(row["MVAR Load"])
    assert load["base_power"] == 100.0
    assert load["power_units"] == "NATURAL_UNITS"
    assert load["conformity"] == "UNDEFINED"


def test_reserves_seven_products_with_minute_units():
    doc, src, reserve_ids = _built_case()
    reserves = pd.read_csv(src / "reserves.csv")

    assert len(reserves) == 7
    assert set(reserve_ids) == set(reserves["Reserve Product"])
    assert len(doc.document.components["OnlineReserve"]) == 7

    by_name = {c["name"]: c for c in doc.document.components["OnlineReserve"]}

    spin1 = by_name["Spin_Up_R1"]
    assert spin1["time_frame"] == 10.0
    assert spin1["sustained_time"] == 60.0
    assert spin1["requirement"] == pytest.approx(40.413)
    assert spin1["reserve_direction"] == "UP"

    flex_up = by_name["Flex_Up"]
    assert flex_up["time_frame"] == 20.0
    assert flex_up["sustained_time"] == 60.0
    assert flex_up["reserve_direction"] == "UP"

    flex_down = by_name["Flex_Down"]
    assert flex_down["reserve_direction"] == "DOWN"

    reg_up = by_name["Reg_Up"]
    assert reg_up["time_frame"] == 5.0
    assert reg_up["sustained_time"] == 60.0

    for name in ("Spin_Up_R1", "Spin_Up_R2", "Spin_Up_R3", "Flex_Up", "Flex_Down", "Reg_Up", "Reg_Down"):
        comp = by_name[name]
        assert comp["max_output_fraction"] == 1.0
        assert comp["max_participation_factor"] == 1.0
        assert comp["deployed_fraction"] == 0.0
        assert comp["available"] is True

    doc.validate()


def test_service_association_counts_per_product():
    doc, src, reserve_ids = _built_case()

    reserve_id_to_name = {v: k for k, v in reserve_ids.items()}
    counts: dict[str, int] = {name: 0 for name in reserve_ids}
    for assoc in doc.document.service_associations:
        name = reserve_id_to_name[assoc.service_id]
        counts[name] += 1

    expected = {
        "Spin_Up_R1": 34,
        "Spin_Up_R2": 25,
        "Spin_Up_R3": 43,
        "Flex_Up": 102,
        "Flex_Down": 102,
        "Reg_Up": 102,
        "Reg_Down": 102,
    }
    assert counts == expected
    assert sum(counts.values()) == 510
    assert len(doc.document.service_associations) == 510

    doc.validate()
