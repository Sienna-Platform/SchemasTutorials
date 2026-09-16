from power_openapi_models.infrastructure_core.models import GeographicInfo, UnitSystem
from power_openapi_models.core.models import Area

from rts_gmlc_case.document import CaseDocument


def test_add_supplemental_attribute_mints_id_and_links_association():
    doc = CaseDocument()
    area = Area(
        id=doc.next_id(),
        name="1",
        base_power=100.0,
        power_units=UnitSystem.NATURAL_UNITS,
    )
    area_id = doc.add_component(area)

    geo = GeographicInfo(id=doc.next_id(), geo_json={"type": "Point"})
    attribute_id = doc.add_supplemental_attribute(
        geo, component_id=area_id, component_type="Area"
    )

    assert attribute_id == geo.id
    assert len(doc.document.supplemental_attributes) == 1
    assert doc.document.supplemental_attributes[0]["geo_json"] == {"type": "Point"}

    assert len(doc.document.supplemental_attribute_associations) == 1
    assoc = doc.document.supplemental_attribute_associations[0]
    assert assoc.component_id == area_id
    assert assoc.component_type == "Area"
    assert assoc.attribute_id == attribute_id
    assert assoc.attribute_type == "GeographicInfo"


def test_add_supplemental_attribute_mints_id_when_unset():
    doc = CaseDocument()
    area_id = doc.add_component(
        Area(id=doc.next_id(), name="1", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS)
    )

    geo = GeographicInfo.model_construct(geo_json={"type": "Point"})
    attribute_id = doc.add_supplemental_attribute(
        geo, component_id=area_id, component_type="Area"
    )

    assert attribute_id == doc.document.supplemental_attributes[0]["id"]
    assert attribute_id not in (None, 0)


def test_supplemental_attribute_not_bucketed_as_a_component():
    doc = CaseDocument()
    area_id = doc.add_component(
        Area(id=doc.next_id(), name="1", base_power=100.0, power_units=UnitSystem.NATURAL_UNITS)
    )
    doc.add_supplemental_attribute(
        GeographicInfo(id=doc.next_id(), geo_json={}),
        component_id=area_id,
        component_type="Area",
    )

    assert "GeographicInfo" not in doc.document.components
    doc.validate()
