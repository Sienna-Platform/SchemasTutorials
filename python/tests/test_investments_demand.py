from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from rts_gmlc_case import data
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.demand import (
    LOAD_DATA_FILE,
    VALUE_OF_LOST_LOAD,
    add_demand_requirements,
)
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.sidecar import SidecarWriter, data_hash
from rts_gmlc_case.topology import add_topology

ZONE_NAMES = {"1", "2", "3"}


def _build(tmp_path: Path):
    doc = CaseDocument()
    op_src = data.rts_source_dir() / "SourceData"
    idx = add_topology(doc, op_src)

    portfolio = PortfolioCase(doc, aggregation="Area", base_system_file="system.json")
    inv_src = investments_data.investments_source_dir()
    inv_idx = add_investment_topology(portfolio, inv_src, idx)

    sidecar = SidecarWriter(tmp_path)
    demand_id_by_zone = add_demand_requirements(portfolio, inv_src, sidecar, inv_idx)
    return doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone


def _load_csv(inv_src: Path) -> pd.DataFrame:
    return pd.read_csv(inv_src / LOAD_DATA_FILE)


def test_exactly_3_demand_requirements_one_per_zone(tmp_path):
    doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone = _build(tmp_path)

    requirements = portfolio.document.components["DemandRequirement"]
    assert len(requirements) == 3
    assert set(demand_id_by_zone) == ZONE_NAMES

    zone_ids = set(inv_idx.zone_id_by_name.values())
    names = set()
    for req in requirements:
        names.add(req["name"])
        assert req["region"] == [inv_idx.zone_id_by_name[req["name"]]]
        assert set(req["region"]) <= zone_ids
        assert req["power_systems_type"] == "PowerLoad"
        assert req["conformity"] == "UNDEFINED"
        assert req["value_of_lost_load"] == VALUE_OF_LOST_LOAD
        # Left unset -- nothing in this task's inputs populates them, so the
        # document omits them rather than restating the schema's own defaults.
        # A reader resolves them from the schema, the same in both languages.
        for field in (
            "new_demand_mw",
            "growth_rate",
            "new_construction_year",
            "unserved_demand_curve",
        ):
            assert field not in req
        # The policy link is an association row, never a field here.
        assert "requirements" not in req
    assert names == ZONE_NAMES


def test_exactly_3_time_series_associations_resolution_pt1h(tmp_path):
    doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone = _build(tmp_path)

    demand_requirement_ids = set(demand_id_by_zone.values())
    assocs = [
        a.root
        for a in portfolio.document.time_series_associations
        if a.root.owner_type == "DemandRequirement"
    ]
    assert len(assocs) == 3
    for sts in assocs:
        assert sts.owner_id in demand_requirement_ids
        assert sts.resolution.root == "PT1H"
        assert sts.name == "requirement"
        assert sts.owner_category.value == "Component"
        assert sts.element_type.root == "f64"
        assert sts.array_shape[0].root == sts.length
        assert sts.time_reference.root == "zoneless"
        assert sts.unit_system.value == "NATURAL_UNITS"
        assert sts.units == "MW"
        assert sts.quantity_kind == "requirement"
        assert sts.features.root == {}


def test_length_matches_a_fresh_csv_read(tmp_path):
    doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone = _build(tmp_path)

    raw = _load_csv(inv_src)
    expected_length = len(raw)
    assert expected_length == 8784  # 366 days x 24 hours, 2020 is a leap year

    assocs = [
        a.root
        for a in portfolio.document.time_series_associations
        if a.root.owner_type == "DemandRequirement"
    ]
    assert len(assocs) == 3
    for sts in assocs:
        assert sts.length == expected_length


def test_uri_exists_and_round_trips_and_data_hash_matches(tmp_path):
    doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone = _build(tmp_path)
    raw = _load_csv(inv_src)

    zone_by_requirement_id = {v: k for k, v in demand_id_by_zone.items()}
    assocs = [
        a.root
        for a in portfolio.document.time_series_associations
        if a.root.owner_type == "DemandRequirement"
    ]
    assert len(assocs) == 3

    for sts in assocs:
        zone_name = zone_by_requirement_id[sts.owner_id]
        expected_values = raw[zone_name].to_numpy(dtype="float64")

        path = tmp_path / sts.uri
        assert path.exists(), f"missing parquet file for association {sts.association_id}"
        table = pq.read_table(path)
        assert table.num_rows == sts.length
        assert table.column("value").to_pylist() == list(expected_values)

        assert sts.data_hash == data_hash(expected_values)


def test_validate_passes(tmp_path):
    doc, portfolio, inv_src, sidecar, inv_idx, demand_id_by_zone = _build(tmp_path)
    doc.validate()
