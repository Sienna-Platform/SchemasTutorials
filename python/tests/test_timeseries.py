from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from rts_gmlc_case import data
from rts_gmlc_case.demand import add_loads, add_reserves
from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.sidecar import SidecarWriter
from rts_gmlc_case.timeseries import (
    TimeSeriesOwners,
    attach_time_series,
    read_profile,
    resolve_case_insensitive_path,
)
from rts_gmlc_case.topology import add_topology


def _write_csv(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


# --- read_profile: Layout A (Period column, object columns) ---------------


def test_read_profile_layout_a_period_resets_daily(tmp_path):
    text = (
        "Year,Month,Day,Period,OBJ_A,OBJ_B\n"
        "2020,1,1,1,10.0,100.0\n"
        "2020,1,1,2,11.0,101.0\n"
        "2020,1,1,3,12.0,102.0\n"
        "2020,1,2,1,13.0,103.0\n"
        "2020,1,2,2,14.0,104.0\n"
        "2020,1,2,3,15.0,105.0\n"
    )
    path = _write_csv(tmp_path, "layout_a.csv", text)

    timestamps, values = read_profile(path, "OBJ_A", pd.Timedelta(hours=1))

    assert list(values) == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    assert timestamps.tz is not None
    expected = pd.DatetimeIndex(
        [
            "2020-01-01T00:00:00Z",
            "2020-01-01T01:00:00Z",
            "2020-01-01T02:00:00Z",
            "2020-01-02T00:00:00Z",
            "2020-01-02T01:00:00Z",
            "2020-01-02T02:00:00Z",
        ]
    )
    assert list(timestamps) == list(expected)

    _, values_b = read_profile(path, "OBJ_B", pd.Timedelta(hours=1))
    assert list(values_b) == [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]


def test_read_profile_layout_a_requires_a_column(tmp_path):
    text = "Year,Month,Day,Period,OBJ_A\n2020,1,1,1,10.0\n"
    path = _write_csv(tmp_path, "layout_a_single.csv", text)
    with pytest.raises(ValueError):
        read_profile(path, None, pd.Timedelta(hours=1))


def test_read_profile_layout_a_unknown_column_raises(tmp_path):
    text = "Year,Month,Day,Period,OBJ_A\n2020,1,1,1,10.0\n"
    path = _write_csv(tmp_path, "layout_a_single2.csv", text)
    with pytest.raises(ValueError):
        read_profile(path, "NOT_A_COLUMN", pd.Timedelta(hours=1))


# --- read_profile: Layout B (no Period column, periods as columns) --------


def test_read_profile_layout_b_flattens_row_major(tmp_path):
    text = (
        "Year,Month,Day,1,2,3\n"
        "2020,1,1,10.0,11.0,12.0\n"
        "2020,1,2,13.0,14.0,15.0\n"
    )
    path = _write_csv(tmp_path, "layout_b.csv", text)

    timestamps, values = read_profile(path, None, pd.Timedelta(hours=1))

    assert list(values) == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    expected = pd.DatetimeIndex(
        [
            "2020-01-01T00:00:00Z",
            "2020-01-01T01:00:00Z",
            "2020-01-01T02:00:00Z",
            "2020-01-02T00:00:00Z",
            "2020-01-02T01:00:00Z",
            "2020-01-02T02:00:00Z",
        ]
    )
    assert list(timestamps) == list(expected)


def test_read_profile_layout_b_ignores_column_argument(tmp_path):
    text = "Year,Month,Day,1,2\n2020,1,1,1.0,2.0\n"
    path = _write_csv(tmp_path, "layout_b_ignore.csv", text)
    _, values = read_profile(path, "does-not-matter", pd.Timedelta(minutes=5))
    assert list(values) == [1.0, 2.0]


# --- resolve_case_insensitive_path: the HYDRO/Hydro fix ------------------
#
# Deliberately does NOT use the real RTS data directory: on macOS's
# case-insensitive filesystem a broken resolver would still "pass" against
# real data, hiding exactly the Linux-breaking bug this exists to catch.
# These build a synthetic tree with a known case mismatch instead.


def test_resolve_case_insensitive_path_finds_mismatched_directory(tmp_path):
    # On-disk directory is "Hydro"; the referenced path says "HYDRO" --
    # mirrors the real RTS-GMLC HYDRO/Hydro mismatch (80 of 282 pointers).
    real_dir = tmp_path / "timeseries_data_files" / "Hydro"
    real_dir.mkdir(parents=True)
    (real_dir / "DAY_AHEAD_hydro.csv").write_text("Year,Month,Day,Period,x\n2020,1,1,1,1.0\n")

    source = tmp_path / "SourceData"
    source.mkdir()

    resolved = resolve_case_insensitive_path(
        source, "../timeseries_data_files/HYDRO/DAY_AHEAD_hydro.csv"
    )

    assert resolved == real_dir / "DAY_AHEAD_hydro.csv"
    assert resolved.exists()


def test_resolve_case_insensitive_path_finds_mismatched_filename(tmp_path):
    # On-disk file is "REAL_TIME_regional_Load.csv"; the referenced path
    # says "REAL_TIME_regional_load.csv" -- mirrors the real RTS-GMLC
    # Load/ filename mismatch.
    real_dir = tmp_path / "timeseries_data_files" / "Load"
    real_dir.mkdir(parents=True)
    (real_dir / "REAL_TIME_regional_Load.csv").write_text("Year,Month,Day,1\n2020,1,1,1.0\n")

    source = tmp_path / "SourceData"
    source.mkdir()

    resolved = resolve_case_insensitive_path(
        source, "../timeseries_data_files/Load/REAL_TIME_regional_load.csv"
    )

    assert resolved == real_dir / "REAL_TIME_regional_Load.csv"
    assert resolved.exists()


def test_resolve_case_insensitive_path_raises_naming_path_when_no_match(tmp_path):
    real_dir = tmp_path / "timeseries_data_files" / "WIND"
    real_dir.mkdir(parents=True)

    source = tmp_path / "SourceData"
    source.mkdir()

    referenced = "../timeseries_data_files/SOLAR/DAY_AHEAD_solar.csv"
    with pytest.raises(ValueError, match="SOLAR"):
        resolve_case_insensitive_path(source, referenced)


# --- attach_time_series: full build on the real RTS-GMLC source data -----


def _built_case(tmp_path: Path):
    doc = CaseDocument()
    src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, src)
    gen_ids = add_generation(doc, src, idx)
    add_loads(doc, src, idx)
    reserve_ids = add_reserves(doc, src, idx, gen_ids)
    sidecar = SidecarWriter(tmp_path)
    owners = TimeSeriesOwners(
        generator_id_by_uid=gen_ids,
        area_id_by_name=idx.area_id_by_name,
        reserve_id_by_product=reserve_ids,
    )
    return doc, src, sidecar, owners


def test_attach_time_series_counts_and_resolutions(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    assocs = doc.document.time_series_associations
    assert len(assocs) == 282

    resolutions = {a.root.resolution.root for a in assocs}
    assert resolutions == {"PT1H", "PT5M"}
    assert doc.document.time_series_storage_file == "timeseries"


def test_attach_time_series_uris_exist_lengths_match_and_dedup_holds(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    assocs = [a.root for a in doc.document.time_series_associations]
    seen_paths: set[Path] = set()
    for sts in assocs:
        path = tmp_path / sts.uri
        assert path.exists(), f"missing parquet file for association {sts.association_id}"
        seen_paths.add(path)
        table = pq.read_table(path)
        assert table.num_rows == sts.length
        assert sts.array_shape[0].root == sts.length

    on_disk = set((tmp_path / "timeseries").glob("*.parquet"))
    assert on_disk == seen_paths  # no orphan parquet files

    # R33: the strongest available assertion. 102 PMin series are
    # byte-identical to their PMax partners, so the sidecar collapses
    # substantially fewer distinct files than the 282 associations.
    assert len(on_disk) < 282
    assert len(on_disk) <= 200


def test_pmax_pmin_dedup_for_122_hydro_1(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    generator_id = owners.generator_id_by_uid["122_HYDRO_1"]
    by_name = {}
    for assoc in doc.document.time_series_associations:
        sts = assoc.root
        if sts.owner_id == generator_id and sts.resolution.root == "PT1H":
            by_name[sts.name] = sts

    pmax = by_name["max_active_power"]
    pmin = by_name["min_active_power"]
    assert pmax.uri == pmin.uri
    assert pmax.data_hash == pmin.data_hash


def test_natural_inflow_resolves_through_storage_csv_to_212_csp_1(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    generator_id = owners.generator_id_by_uid["212_CSP_1"]
    inflow = [
        a.root
        for a in doc.document.time_series_associations
        if a.root.owner_id == generator_id and a.root.name == "inflow"
    ]
    assert len(inflow) == 2  # DAY_AHEAD + REAL_TIME
    for series in inflow:
        assert series.owner_type == "RenewableDispatch"
        assert series.quantity_kind == "power"


def test_owner_category_counts_generator_reserve_area(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    generator_ids = set(owners.generator_id_by_uid.values())
    reserve_ids = set(owners.reserve_id_by_product.values())
    area_ids = set(owners.area_id_by_name.values())

    counts = {"Generator": 0, "Reserve": 0, "Area": 0}
    for assoc in doc.document.time_series_associations:
        sts = assoc.root
        assert sts.owner_category.value == "Component"
        assert sts.element_type.root == "f64"
        assert sts.time_reference.root == "zoneless"
        assert sts.unit_system.value == "NATURAL_UNITS"
        if sts.owner_id in generator_ids and sts.owner_type != "Area":
            counts["Generator"] += 1
        elif sts.owner_id in reserve_ids and sts.owner_type == "OnlineReserve":
            counts["Reserve"] += 1
        elif sts.owner_id in area_ids and sts.owner_type == "Area":
            counts["Area"] += 1

    assert counts == {"Generator": 264, "Reserve": 12, "Area": 6}


def test_scaling_factor_applied_to_values(tmp_path):
    doc, src, sidecar, owners = _built_case(tmp_path)
    attach_time_series(doc, src, sidecar, owners)

    pointers = pd.read_csv(src / "timeseries_pointers.csv")
    row = pointers[
        (pointers["Category"] == "Generator")
        & (pointers["Object"] == "122_HYDRO_1")
        & (pointers["Parameter"] == "PMax MW")
        & (pointers["Simulation"] == "DAY_AHEAD")
    ].iloc[0]

    raw = pd.read_csv(src / row["Data File"])
    expected_first = float(raw["122_HYDRO_1"].iloc[0]) * float(row["Scaling Factor"])

    generator_id = owners.generator_id_by_uid["122_HYDRO_1"]
    sts = next(
        a.root
        for a in doc.document.time_series_associations
        if a.root.owner_id == generator_id
        and a.root.name == "max_active_power"
        and a.root.resolution.root == "PT1H"
    )
    table = pq.read_table(tmp_path / sts.uri)
    assert table.column("value").to_pylist()[0] == pytest.approx(expected_first)
