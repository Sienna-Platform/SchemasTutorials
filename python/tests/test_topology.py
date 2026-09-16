import math

import pandas as pd

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import add_topology


def test_topology_counts_from_source():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    bus = pd.read_csv(src / "bus.csv")

    assert len(doc.document.components["ACBus"]) == len(bus)
    assert len(doc.document.components["Area"]) == bus["Area"].nunique()
    assert len(doc.document.components["LoadZone"]) == bus["Zone"].nunique()

    # Pinned expected totals (CAMPAIGN-FACTS.md "Expected component counts").
    assert len(doc.document.components["ACBus"]) == 73
    assert len(doc.document.components["Area"]) == 3
    assert len(doc.document.components["LoadZone"]) == 21
    assert len(doc.document.components["FixedAdmittance"]) == 3

    abel = next(c for c in doc.document.components["ACBus"] if c["number"] == 101)
    assert abel["name"] == "Abel"
    expected_angle = math.radians(bus.loc[bus["Bus ID"] == 101, "V Angle"].iloc[0])
    assert abs(abel["angle"] - expected_angle) < 1e-12
    assert abel["voltage_limits"] == {"min": 0.95, "max": 1.05}
    assert abel["available"] is True

    shunt_names = {c["name"] for c in doc.document.components["FixedAdmittance"]}
    assert shunt_names == {"Alber_shunt", "Bajer_shunt", "Camus_shunt"}
    for shunt in doc.document.components["FixedAdmittance"]:
        assert shunt["Y"]["real"] == 0.0
        assert shunt["Y"]["imag"] == -100.0
        assert shunt["admittance_units"] == "NATURAL_UNITS"

    ref_buses = [c for c in doc.document.components["ACBus"] if c["bustype"] == "REF"]
    assert len(ref_buses) >= 1

    area_load = bus.groupby("Area")[["MW Load", "MVAR Load"]].sum()
    for area in doc.document.components["Area"]:
        expected_p = float(area_load.loc[int(area["name"]), "MW Load"])
        expected_q = float(area_load.loc[int(area["name"]), "MVAR Load"])
        assert area["peak_active_power"] == expected_p
        assert area["peak_reactive_power"] == expected_q
        assert area["peak_active_power"] != 0.0
        assert area["load_response"] == 0.0
    total_system_load = float(bus["MW Load"].sum())
    assert {a["peak_active_power"] for a in doc.document.components["Area"]} == {
        total_system_load / bus["Area"].nunique()
    }

    zone_load = bus.groupby("Zone")[["MW Load", "MVAR Load"]].sum()
    zone_peak_active_sum = 0.0
    for zone in doc.document.components["LoadZone"]:
        expected_p = float(zone_load.loc[float(zone["name"]), "MW Load"])
        expected_q = float(zone_load.loc[float(zone["name"]), "MVAR Load"])
        assert zone["peak_active_power"] == expected_p
        assert zone["peak_reactive_power"] == expected_q
        assert zone["peak_active_power"] != 0.0
        zone_peak_active_sum += zone["peak_active_power"]
    assert zone_peak_active_sum == total_system_load

    doc.validate()

    assert set(idx.bus_id_by_number) == set(bus["Bus ID"].tolist())
    assert set(idx.area_id_by_name) == {str(int(a)) for a in bus["Area"].unique()}
    assert set(idx.zone_id_by_name) == {str(int(z)) for z in bus["Zone"].unique()}

    # Areas and zones were added in sorted order — ids increase with name.
    sorted_area_ids = [idx.area_id_by_name[name] for name in sorted(idx.area_id_by_name, key=int)]
    assert sorted_area_ids == sorted(sorted_area_ids)
    sorted_zone_ids = [idx.zone_id_by_name[name] for name in sorted(idx.zone_id_by_name, key=int)]
    assert sorted_zone_ids == sorted(sorted_zone_ids)
