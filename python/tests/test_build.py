"""Task 9: the driver. Builds the whole RTS-GMLC case end to end, reads it
back, and proves the build is deterministic and complete.

Most tests here run one real, full build (all 282 time-series profiles,
some ~105k rows) via a module-scoped fixture shared across the tests that
only need to *read* the built case, so the expensive build happens once per
test-file run; the determinism test additionally runs a second full build,
since byte-identity across two independent builds is the whole point.
All of them are marked ``slow`` -- deselect with ``-m "not slow"`` to skip
them while still running the fast per-stage unit tests elsewhere in this
test suite. The CLI argument-parsing test at the bottom needs no RTS data
and is not marked ``slow``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from rts_gmlc_case.build import build_case, read_case

EXPECTED_COMPONENT_COUNTS = {
    "ACBus": 73,
    "Area": 3,
    "LoadZone": 21,
    "FixedAdmittance": 3,
    "Arc": 109,
    "Line": 105,
    "TransformerCircuit": 15,
    "TwoWindingTransformer": 15,
    "TwoTerminalGenericHVDCLine": 1,
    "PowerLoad": 51,
    "ThermalStandard": 73,
    "RenewableDispatch": 30,
    "RenewableNonDispatch": 31,
    "HydroDispatch": 20,
    "SynchronousCondenser": 3,
    "EnergyReservoirStorage": 1,
    "OnlineReserve": 7,
}
EXPECTED_SERVICE_ASSOCIATIONS = 510
EXPECTED_TIME_SERIES_ASSOCIATIONS = 282


@pytest.fixture(scope="module")
def built_case(tmp_path_factory: pytest.TempPathFactory):
    case_dir = tmp_path_factory.mktemp("rts-case")
    doc = build_case(case_dir)
    return case_dir, doc


@pytest.mark.slow
def test_build_case_produces_expected_component_counts(built_case):
    case_dir, doc = built_case

    counts = {name: len(items) for name, items in doc.document.components.items()}
    assert counts == EXPECTED_COMPONENT_COUNTS
    assert len(doc.document.service_associations) == EXPECTED_SERVICE_ASSOCIATIONS
    assert len(doc.document.time_series_associations) == EXPECTED_TIME_SERIES_ASSOCIATIONS
    assert (case_dir / "system.json").is_file()


@pytest.mark.slow
def test_id_uniqueness_across_the_whole_document(built_case):
    _, doc = built_case

    owner_by_id: dict[int, str] = {}
    for type_name, items in doc.document.components.items():
        for item in items:
            item_id = item["id"]
            assert item_id not in owner_by_id, (
                f"id {item_id} reused: already {owner_by_id[item_id]}, now {type_name}"
            )
            owner_by_id[item_id] = type_name


@pytest.mark.slow
def test_round_trip_typed_components_match_bucket_by_bucket(built_case):
    case_dir, built_doc = built_case
    read_doc = read_case(case_dir)

    built_typed = built_doc.typed_components()
    read_typed = read_doc.typed_components()

    assert set(built_typed) == set(read_typed)
    for type_name in sorted(built_typed):
        built_dumps = [m.model_dump(mode="json") for m in built_typed[type_name]]
        read_dumps = [m.model_dump(mode="json") for m in read_typed[type_name]]
        assert built_dumps == read_dumps, f"bucket {type_name!r} mismatched after round-trip"


@pytest.mark.slow
def test_sidecar_has_no_orphans_and_lengths_match_row_counts(built_case):
    case_dir, doc = built_case

    assocs = [assoc.root for assoc in doc.document.time_series_associations]
    seen_paths: set[Path] = set()
    for assoc in assocs:
        path = case_dir / assoc.uri
        assert path.is_file(), f"missing parquet file for association {assoc.association_id}"
        seen_paths.add(path)
        table = pq.read_table(path)
        assert table.num_rows == assoc.length

    on_disk = set((case_dir / "timeseries").glob("*.parquet"))
    assert on_disk == seen_paths  # no orphan parquet files
    # R33's dedup check: 102 PMin series are byte-identical to their PMax
    # partners, so distinct files are substantially fewer than 282.
    assert len(on_disk) < EXPECTED_TIME_SERIES_ASSOCIATIONS


@pytest.mark.slow
def test_build_is_byte_deterministic(built_case, tmp_path_factory: pytest.TempPathFactory):
    case_dir_a, _ = built_case
    case_dir_b = tmp_path_factory.mktemp("rts-case-determinism-rebuild")
    build_case(case_dir_b)

    bytes_a = (case_dir_a / "system.json").read_bytes()
    bytes_b = (case_dir_b / "system.json").read_bytes()
    assert bytes_a == bytes_b


# --- fast: CLI argument handling needs no RTS data or build -----------------


def test_cli_reports_usage_error_without_output_dir():
    build_rts_path = Path(__file__).resolve().parents[1] / "build_rts.py"
    result = subprocess.run(
        [sys.executable, str(build_rts_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
