import pytest
from power_openapi_models.infrastructure_core.models import UnitSystem
from power_openapi_models.core.models import ACBus, Arc, Area

from rts_gmlc_case.document import CaseDocument


def _area(doc: CaseDocument, name: str) -> Area:
    return Area(
        id=doc.next_id(),
        name=name,
        base_power=100.0,
        power_units=UnitSystem.NATURAL_UNITS,
    )


def test_add_component_mints_id_and_buckets_by_type_name():
    doc = CaseDocument()
    area_id = doc.add_component(_area(doc, "1"))
    assert area_id == 1
    assert [c["name"] for c in doc.document.components["Area"]] == ["1"]


def test_validate_passes_when_references_resolve():
    doc = CaseDocument()
    bus_a = ACBus(id=doc.next_id(), number=101, name="bus-a", available=True)
    bus_b = ACBus(id=doc.next_id(), number=102, name="bus-b", available=True)
    doc.add_component(bus_a)
    doc.add_component(bus_b)
    doc.add_component(Arc(id=doc.next_id(), from_id=bus_a.id, to_id=bus_b.id))
    doc.validate()


def test_dangling_reference_rejected():
    doc = CaseDocument()
    doc.add_component(Arc(id=doc.next_id(), from_id=999, to_id=998))
    with pytest.raises(ValueError, match="unresolved"):
        doc.validate()


def test_duplicate_id_rejected():
    doc = CaseDocument()
    doc.add_component(Area(id=1, name="a", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS))
    doc.add_component(Area(id=1, name="b", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS))
    with pytest.raises(ValueError, match="duplicate"):
        doc.validate()


def test_write_read_roundtrip_and_typed_reparse(tmp_path):
    doc = CaseDocument()
    area = _area(doc, "1")
    doc.add_component(area)
    doc.validate()

    path = tmp_path / "system.json"
    doc.write(path)
    assert path.is_file()

    loaded = CaseDocument.read(path)
    typed = loaded.typed_components()
    assert isinstance(typed["Area"][0], Area)
    assert typed["Area"][0].name == "1"
    assert loaded.next_id() == 2
