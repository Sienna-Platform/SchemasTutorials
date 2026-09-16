"""Task E6: the combined driver. Builds the whole operations + investments
RTS-GMLC capacity-expansion case end to end, reads it back, and proves the
cross-cutting correctness properties the plan calls out explicitly:
byte-determinism, global id uniqueness across both halves, every
investments reference resolving inside the same document, no sidecar
orphans, and every ``power_systems_type`` string naming a type actually
present in the document.

Most tests here run one real, full build (operations' ~282 time-series
profiles plus the investments demand time series, all real downloaded RTS
data) via a module-scoped fixture shared across the tests that only need to
*read* the built case, so the expensive build happens once per test-file
run; the determinism test additionally runs a second full build, since
byte-identity across two independent builds is the whole point. All of
these are marked ``slow`` -- deselect with ``-m "not slow"`` to skip them.
The CLI argument-parsing test at the bottom needs no RTS data and is not
marked ``slow``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rts_gmlc_case.investments.build import build_expansion_case, read_expansion_case

# Operations-side counts, unchanged from `test_build.py`'s own
# `EXPECTED_COMPONENT_COUNTS`/`EXPECTED_SERVICE_ASSOCIATIONS`/
# `EXPECTED_TIME_SERIES_ASSOCIATIONS` (duplicated rather than imported
# cross-module: `tests/` has no `__init__.py`, so it isn't reliably
# importable as a package under pytest's default import mode).
OPERATIONS_EXPECTED_COMPONENT_COUNTS = {
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
OPERATIONS_EXPECTED_SERVICE_ASSOCIATIONS = 510
OPERATIONS_EXPECTED_TIME_SERIES_ASSOCIATIONS = 282

# Investments-side counts, in the *portfolio* document. E1 mints no
# components at all -- the schema has no Node and no Zone, so the zones a
# technology's `region` points at are the operations Areas in the base
# system. 9 SupplyTechnology (E2); 1 StorageTechnology, 108
# NodalACTransportTechnology, 1 NodalHVDCTransportTechnology (E3); 3
# DemandRequirement (E4); 4 CarbonCaps + 1 each of CarbonTax/
# CapacityReserveMargin/EnergyShareRequirements/MinimumCapacityRequirements/
# MaximumCapacityRequirements (E5, 9 total).
INVESTMENTS_EXPECTED_COMPONENT_COUNTS = {
    "SupplyTechnology": 9,
    "StorageTechnology": 1,
    "NodalACTransportTechnology": 108,
    "NodalHVDCTransportTechnology": 1,
    "DemandRequirement": 3,
    "CarbonCaps": 4,
    "CarbonTax": 1,
    "CapacityReserveMargin": 1,
    "EnergyShareRequirements": 1,
    "MinimumCapacityRequirements": 1,
    "MaximumCapacityRequirements": 1,
}
# 3 DemandRequirement time-series associations, in the portfolio; the
# operations 282 stay in the system document.
INVESTMENTS_EXPECTED_TIME_SERIES_ASSOCIATIONS = 3

# The fields on investments component classes that reference another
# component's id, per class -- `CaseDocument.validate()` does not check
# these (confirmed: none are in `document.py`'s `_REFERENCE_FIELDS`), so
# this module checks them directly. The 6 policy types have no reference
# fields of their own (confirmed by reading `investments/models.py`) and so
# are not included here.
INVESTMENTS_REFERENCE_FIELDS_BY_TYPE = {
    "SupplyTechnology": ("region",),
    "StorageTechnology": ("region",),
    "NodalACTransportTechnology": ("start_node", "end_node"),
    "NodalHVDCTransportTechnology": ("start_node", "end_node"),
    "DemandRequirement": ("region",),
}

# Every investments component with a `power_systems_type` field, and the
# string each is expected to carry (per E2/E3/E4's reports' R39 convention).
POWER_SYSTEMS_TYPE_BY_TYPE = {
    "StorageTechnology": "EnergyReservoirStorage",
    "NodalACTransportTechnology": "Line",
    "NodalHVDCTransportTechnology": "TwoTerminalGenericHVDCLine",
    "DemandRequirement": "PowerLoad",
}


@pytest.fixture(scope="module")
def built_case(tmp_path_factory: pytest.TempPathFactory):
    case_dir = tmp_path_factory.mktemp("rts-expansion-case")
    doc, portfolio = build_expansion_case(case_dir)
    return case_dir, doc, portfolio


@pytest.mark.slow
def test_expansion_build_produces_expected_component_counts(built_case):
    case_dir, doc, portfolio = built_case

    system_counts = {name: len(items) for name, items in doc.document.components.items()}
    assert system_counts == OPERATIONS_EXPECTED_COMPONENT_COUNTS
    assert len(doc.document.service_associations) == OPERATIONS_EXPECTED_SERVICE_ASSOCIATIONS
    assert (
        len(doc.document.time_series_associations)
        == OPERATIONS_EXPECTED_TIME_SERIES_ASSOCIATIONS
    )

    portfolio_counts = {
        name: len(items) for name, items in portfolio.document.components.items()
    }
    assert portfolio_counts == INVESTMENTS_EXPECTED_COMPONENT_COUNTS
    assert (
        len(portfolio.document.time_series_associations)
        == INVESTMENTS_EXPECTED_TIME_SERIES_ASSOCIATIONS
    )

    # The pair is written side by side, and the portfolio names its base.
    assert (case_dir / "system.json").is_file()
    assert (case_dir / "portfolio.json").is_file()
    assert portfolio.document.base_system_file == "system.json"


@pytest.mark.slow
def test_id_uniqueness_spans_operations_and_investments_in_one_continuous_space(built_case):
    _, doc, portfolio = built_case

    all_ids: set[int] = set()
    total_components = 0
    owner_by_id: dict[int, str] = {}
    buckets = list(doc.document.components.items()) + list(
        portfolio.document.components.items()
    )
    for type_name, items in buckets:
        for item in items:
            item_id = item["id"]
            assert item_id not in all_ids, (
                f"id {item_id} reused: already {owner_by_id[item_id]}, now {type_name}"
            )
            all_ids.add(item_id)
            owner_by_id[item_id] = type_name
            total_components += 1

    assert len(all_ids) == total_components

    # Not two independent counters that happen not to collide: prove the
    # system's and the portfolio's ids are drawn from the same space, in
    # build order (every ACBus/ThermalStandard id is smaller than every
    # SupplyTechnology id, since operations stages run first). This is what
    # makes a technology's `region` unambiguous across the document pair.
    ac_bus_ids = {item["id"] for item in doc.document.components["ACBus"]}
    thermal_ids = {item["id"] for item in doc.document.components["ThermalStandard"]}
    supply_ids = {item["id"] for item in portfolio.document.components["SupplyTechnology"]}
    assert ac_bus_ids and thermal_ids and supply_ids
    assert max(ac_bus_ids | thermal_ids) < min(supply_ids)


@pytest.mark.slow
def test_every_investment_reference_resolves_to_a_component_in_the_document(built_case):
    _, doc, portfolio = built_case

    # References may land in either document -- a `region` names an Area or
    # ACBus in the base system -- so both id spaces are in scope.
    all_ids = {
        item["id"]
        for items in list(doc.document.components.values())
        + list(portfolio.document.components.values())
        for item in items
    }

    checked_any = False
    for type_name, fields in INVESTMENTS_REFERENCE_FIELDS_BY_TYPE.items():
        items = portfolio.document.components[type_name]
        assert items, f"expected at least one {type_name} component"
        for item in items:
            for field in fields:
                value = item.get(field)
                if value is None:
                    continue
                refs = value if isinstance(value, list) else [value]
                for ref_id in refs:
                    checked_any = True
                    assert ref_id in all_ids, (
                        f"{type_name} id={item['id']} field {field!r} references "
                        f"missing id {ref_id}"
                    )
    assert checked_any, "expected at least one populated reference field to check"


@pytest.mark.slow
def test_sidecar_has_no_orphans_in_either_direction(built_case):
    case_dir, doc, portfolio = built_case

    assocs = [
        assoc.root
        for assoc in doc.document.time_series_associations
        + portfolio.document.time_series_associations
    ]
    referenced_paths = {case_dir / assoc.uri for assoc in assocs}
    for path in referenced_paths:
        assert path.is_file(), f"association references a missing file: {path}"

    on_disk = set((case_dir / "timeseries").glob("*.parquet"))
    assert on_disk == referenced_paths


@pytest.mark.slow
def test_power_systems_type_values_all_name_types_present_in_the_document(built_case):
    _, doc, portfolio = built_case

    # `power_systems_type` names an operations type, so it resolves against
    # the base system's buckets, not the portfolio's.
    supply_types = {
        item["power_systems_type"]
        for item in portfolio.document.components["SupplyTechnology"]
    }
    assert supply_types, "expected at least one SupplyTechnology"
    for type_name in supply_types:
        assert type_name in doc.document.components
        assert len(doc.document.components[type_name]) > 0

    for owner_type, expected_type_name in POWER_SYSTEMS_TYPE_BY_TYPE.items():
        items = portfolio.document.components[owner_type]
        assert items, f"expected at least one {owner_type} component"
        for item in items:
            assert item["power_systems_type"] == expected_type_name
        assert expected_type_name in doc.document.components
        assert len(doc.document.components[expected_type_name]) > 0


@pytest.mark.slow
def test_round_trip_typed_components_match_bucket_by_bucket(built_case):
    """Proves the `document.py` `_MODEL_MODULES` fix: every investments
    component type re-parses through `typed_components()` without raising,
    and round-trips byte-for-byte through a full write/read cycle.
    """
    case_dir, _, built_portfolio = built_case
    _, read_portfolio = read_expansion_case(case_dir)

    built_typed = built_portfolio.typed_components()
    read_typed = read_portfolio.typed_components()

    assert set(built_typed) == set(read_typed)
    assert set(INVESTMENTS_EXPECTED_COMPONENT_COUNTS) <= set(built_typed)
    for type_name in sorted(built_typed):
        built_dumps = [m.model_dump(mode="json") for m in built_typed[type_name]]
        read_dumps = [m.model_dump(mode="json") for m in read_typed[type_name]]
        assert built_dumps == read_dumps, f"bucket {type_name!r} mismatched after round-trip"


@pytest.mark.slow
def test_build_is_byte_deterministic(built_case, tmp_path_factory: pytest.TempPathFactory):
    case_dir_a, _, _ = built_case
    case_dir_b = tmp_path_factory.mktemp("rts-expansion-case-determinism-rebuild")
    build_expansion_case(case_dir_b)

    bytes_a = (case_dir_a / "system.json").read_bytes()
    bytes_b = (case_dir_b / "system.json").read_bytes()
    assert bytes_a == bytes_b

    names_a = {p.name for p in (case_dir_a / "timeseries").glob("*.parquet")}
    names_b = {p.name for p in (case_dir_b / "timeseries").glob("*.parquet")}
    assert names_a == names_b
    assert names_a  # non-empty: something was actually written


# --- fast: CLI argument handling needs no RTS data or build -----------------


def test_cli_reports_usage_error_without_output_dir():
    build_expansion_path = Path(__file__).resolve().parents[1] / "build_expansion.py"
    result = subprocess.run(
        [sys.executable, str(build_expansion_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
