"""The policy-to-technology link is an association row, not a field.

An earlier draft of this tutorial pushed a policy id onto a ``requirements``
list on the technology component itself. No release of SiennaSchemas has ever
defined that field; the membership belongs in
``PortfolioDocument.requirements_associations``, one row per (requirement,
member) pair. These tests pin that.
"""

import pytest

from power_openapi_models.investments.models import CarbonCaps, SupplyTechnology

from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.investments.costs import financial_data_for


def _portfolio() -> PortfolioCase:
    return PortfolioCase(CaseDocument(), aggregation="Area", base_system_file="system.json")


def _supply_technology(doc: PortfolioCase, name: str = "gas-cc") -> int:
    return doc.add_component(
        SupplyTechnology(
            id=doc.next_id(),
            name=name,
            power_systems_type="ThermalStandard",
            region=[1],
            prime_mover_type=None,
            financial_data=financial_data_for("gas-cc"),
        )
    )


def _carbon_cap(doc: PortfolioCase, name: str = "Carbon cap 2025") -> int:
    return doc.add_component(
        CarbonCaps(id=doc.next_id(), name=name, available=True, max_mtons=8.0)
    )


def test_association_row_records_the_pair():
    doc = _portfolio()
    technology_id = _supply_technology(doc)
    policy_id = _carbon_cap(doc)

    doc.add_requirement_association(requirement_id=policy_id, entity_id=technology_id)

    rows = doc.document.requirements_associations
    assert len(rows) == 1
    assert rows[0].requirement_id == policy_id
    assert rows[0].entity_id == technology_id


def test_the_technology_component_carries_no_requirements_key():
    doc = _portfolio()
    technology_id = _supply_technology(doc)
    policy_id = _carbon_cap(doc)
    doc.add_requirement_association(requirement_id=policy_id, entity_id=technology_id)

    technology = doc.document.components["SupplyTechnology"][0]
    assert "requirements" not in technology


def test_one_policy_can_bind_many_technologies():
    doc = _portfolio()
    first = _supply_technology(doc, "gas-cc")
    second = _supply_technology(doc, "coal")
    policy_id = _carbon_cap(doc)

    doc.add_requirement_association(requirement_id=policy_id, entity_id=first)
    doc.add_requirement_association(requirement_id=policy_id, entity_id=second)

    pairs = {(r.requirement_id, r.entity_id) for r in doc.document.requirements_associations}
    assert pairs == {(policy_id, first), (policy_id, second)}


def test_duplicate_pair_is_rejected_not_collapsed():
    doc = _portfolio()
    technology_id = _supply_technology(doc)
    policy_id = _carbon_cap(doc)
    doc.add_requirement_association(requirement_id=policy_id, entity_id=technology_id)

    with pytest.raises(ValueError, match="duplicate requirement membership"):
        doc.add_requirement_association(requirement_id=policy_id, entity_id=technology_id)


def test_validate_rejects_an_association_naming_a_missing_id():
    doc = _portfolio()
    technology_id = _supply_technology(doc)
    doc.add_requirement_association(requirement_id=999_999, entity_id=technology_id)

    with pytest.raises(ValueError, match="unresolved requirement association"):
        doc.validate()
