import pandas as pd
import pytest

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.generation import UNIT_TYPE_TO_MODEL, add_generation
from rts_gmlc_case.topology import TopologyIndex, add_topology


def test_generation_counts_match_gen_csv_groupby():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    generator_id_by_uid = add_generation(doc, src, idx)

    gen = pd.read_csv(src / "gen.csv")

    # Every Unit Type in the source is covered by the table (R4: ROR included).
    assert set(gen["Unit Type"]) == set(UNIT_TYPE_TO_MODEL)
    assert len(UNIT_TYPE_TO_MODEL) == 12

    # Counts derived from a fresh group-by, not copied from the mapping.
    expected_counts = gen["Unit Type"].map(UNIT_TYPE_TO_MODEL).value_counts().to_dict()
    for target, expected in expected_counts.items():
        assert len(doc.document.components[target]) == expected

    # Pinned totals (CAMPAIGN-FACTS.md "Expected component counts", R4).
    assert len(doc.document.components["ThermalStandard"]) == 73
    assert len(doc.document.components["RenewableDispatch"]) == 30
    assert len(doc.document.components["RenewableNonDispatch"]) == 31
    assert len(doc.document.components["HydroDispatch"]) == 20
    assert len(doc.document.components["SynchronousCondenser"]) == 3
    assert len(doc.document.components["EnergyReservoirStorage"]) == 1

    assert len(generator_id_by_uid) == len(gen) == 158
    assert generator_id_by_uid["101_CT_1"] in {
        c["id"] for c in doc.document.components["ThermalStandard"]
    }

    doc.validate()


def test_ct1_thermal_cost_and_ratings():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    add_generation(doc, src, idx)

    ct1 = next(c for c in doc.document.components["ThermalStandard"] if c["name"] == "101_CT_1")

    assert ct1["base_power"] == 24.0
    assert ct1["rating"] == 22.360679774997898
    assert ct1["time_limits"] == {"up": 60.0, "down": 60.0}
    assert ct1["fuel"] == "DISTILLATE_FUEL_OIL"
    assert ct1["prime_mover_type"] == "CT"

    cost = ct1["operation_cost"]
    assert cost["cost_type"] == "THERMAL"
    assert cost["shut_down"] == 0.0
    assert cost["start_up"] == 51.747

    variable = cost["variable_operation_cost"]
    assert variable["variable_cost_type"] == "FUEL"
    assert variable["fuel_cost"] == 0.0103494

    curve = variable["value_curve"]
    assert curve["curve_type"] == "INCREMENTAL"
    assert curve["function_data"]["function_type"] == "PIECEWISE_STEP"
    assert curve["function_data"]["x_coords"] == [8.0, 12.0, 16.0, 20.0]
    assert curve["function_data"]["y_coords"] == [9456.0, 9476.0, 10352.0]
    assert curve["initial_input"] == 104912.0

    doc.validate()


def test_renewable_and_hydro_ratings_and_conventions():
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    add_generation(doc, src, idx)

    gen = pd.read_csv(src / "gen.csv")

    # RenewableDispatch/RenewableNonDispatch: rating == base_power == Base MVA == PMax MW (R26).
    for target in ("RenewableDispatch", "RenewableNonDispatch"):
        for comp in doc.document.components[target]:
            assert comp["rating"] == comp["base_power"]

    # HydroDispatch: rating is hypot(PMax, QMax), not Base MVA (R26).
    ror = next(c for c in doc.document.components["HydroDispatch"] if c["name"] == "201_HYDRO_4")
    assert ror["rating"] == 52.49761899362675
    assert ror["base_power"] == 53.0
    assert ror["prime_mover_type"] == "HY"

    # SynchronousCondenser: rating == QMax MVAR, base_power hardcoded to 100.0 (R26).
    for comp in doc.document.components["SynchronousCondenser"]:
        row = gen[gen["GEN UID"] == comp["name"]].iloc[0]
        assert comp["rating"] == float(row["QMax MVAR"])
        assert comp["base_power"] == 100.0
        assert "prime_mover_type" not in comp

    # EnergyReservoirStorage: rating from storage.csv Rating MVA; efficiency from the
    # source's real 85% roundtrip figure, split as sqrt(0.85) per leg (R27), not 1.0/1.0.
    storage = next(iter(doc.document.components["EnergyReservoirStorage"]))
    assert storage["rating"] == 50.0
    assert storage["efficiency"]["in"] == pytest.approx(0.85**0.5)
    assert storage["efficiency"]["out"] == pytest.approx(0.85**0.5)

    doc.validate()


def test_unmapped_unit_type_errors_loudly_naming_the_row(tmp_path):
    (tmp_path / "gen.csv").write_text(
        "GEN UID,Bus ID,Unit Type\n999_BOGUS_1,101,NOT_A_REAL_TYPE\n"
    )
    (tmp_path / "storage.csv").write_text(
        "GEN UID,Storage,Max Volume GWh,Initial Volume GWh,"
        "Start Energy,Inflow Limit GWh,Rating MVA,position\n"
    )
    doc = CaseDocument()
    idx = TopologyIndex(bus_id_by_number={}, area_id_by_name={}, zone_id_by_name={})

    with pytest.raises(ValueError, match="999_BOGUS_1"):
        add_generation(doc, tmp_path, idx)
    with pytest.raises(ValueError, match="NOT_A_REAL_TYPE"):
        add_generation(doc, tmp_path, idx)


def test_unmapped_thermal_fuel_errors_loudly_naming_the_row(tmp_path):
    (tmp_path / "gen.csv").write_text(
        "GEN UID,Bus ID,Unit Type,Fuel\n101_CT_1,101,CT,UNOBTANIUM\n"
    )
    (tmp_path / "storage.csv").write_text(
        "GEN UID,Storage,Max Volume GWh,Initial Volume GWh,"
        "Start Energy,Inflow Limit GWh,Rating MVA,position\n"
    )
    doc = CaseDocument()
    idx = TopologyIndex(bus_id_by_number={101: 1}, area_id_by_name={}, zone_id_by_name={})

    with pytest.raises(ValueError, match="101_CT_1"):
        add_generation(doc, tmp_path, idx)
    with pytest.raises(ValueError, match="UNOBTANIUM"):
        add_generation(doc, tmp_path, idx)
