"""The document layer: id minting, component bucketing, reference validation,
and typed re-parse on top of the shipped ``SystemDocument`` container.

``power_openapi_models.document`` already ships the container itself
(``SystemDocument``, ``read_document``, ``write_document``); this module does
NOT reimplement it. A ``SystemDocument`` has these top-level JSON keys —
identical, field for field, to the Julia ``SystemDocument``
(``PowerOpenAPIModels.jl/src/document.jl``):

    name, description, frequency, components, supplemental_attributes,
    supplemental_attribute_associations, plant_associations,
    combined_cycle_associations, service_associations,
    trading_hub_associations, time_series_associations, ext,
    time_series_storage_file

There is no document-level ``base_power`` or ``unit_system`` in either
package: every component carries its own ``base_power`` and ``power_units``
(see the campaign's R12/R12a rulings). ``components`` is untyped —
``dict[str, list[dict]]``, bucketed by the producing class's ``__name__`` —
and component ids are plain Python ``int``.

What is added here, the part the package genuinely lacks:

- Sequential integer id minting. Julia's ``SystemDocument`` keeps an id
  counter internally; Python's does not. That asymmetry is real, not an
  oversight, so this module owns the counter instead.
- ``CaseDocument.add_component`` — buckets a component by
  ``type(model).__name__`` and returns its id.
- ``CaseDocument.add_supplemental_attribute`` — appends a supplemental
  attribute plus its ``SupplementalAttributeAssociation`` row, and returns
  the attribute's id.
- ``PortfolioCase`` — the same builder for a ``PortfolioDocument``, the
  container an investments case belongs in. It shares the operations
  ``CaseDocument``'s id counter, so a technology's ``region`` can name an
  ``ACBus`` or ``Area`` id in the base system and stay unambiguous.
- ``CaseDocument.validate`` — checks every component id is unique and every
  known integer reference field resolves to an id that exists.
- ``CaseDocument.typed_components`` — turns the untyped ``components``
  buckets back into pydantic model instances via a registry built from the
  domain modules (``core``, ``operations``, ``timeseries``,
  ``infrastructure_core``, ``investments``). Task 9's ``read_case`` depends
  on this.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from pydantic import BaseModel

from power_openapi_models.document import (
    PortfolioDocument,
    SystemDocument,
    read_document,
    read_portfolio_document,
    write_document,
    write_portfolio_document,
)
from power_openapi_models.investments.models import RequirementAssociation
from power_openapi_models.infrastructure_core.models import SupplementalAttributeAssociation
from power_openapi_models.operations.models import ServiceAssociation

_MODEL_MODULES = ("core", "operations", "timeseries", "infrastructure_core", "investments")

# Integer fields on component classes (not association classes, which live in
# the document's other top-level lists, not in `components`) that reference
# another component's id. Starts from the task brief's set (`bus`, `arc`,
# `area`, `load_zone`, `circuit`, `from_id`, `to_id`, `owner_id`) and extends
# it with the other bus/component references found in operations.models and
# dynamics.models: `dynamic_injector` (generator -> its dynamic model),
# `dc_bus`/`star_bus` (converter/transformer terminal buses), `bus_control`
# and the `remote_bus_control*` variants (regulated/controlled bus refs).
_REFERENCE_FIELDS = (
    "bus",
    "arc",
    "area",
    "load_zone",
    "circuit",
    "from_id",
    "to_id",
    "owner_id",
    "dynamic_injector",
    "dc_bus",
    "star_bus",
    "bus_control",
    "remote_bus_control",
    "remote_bus_control_from",
    "remote_bus_control_to",
)


def _build_registry() -> dict[str, type[BaseModel]]:
    registry: dict[str, type[BaseModel]] = {}
    for module_name in _MODEL_MODULES:
        module = importlib.import_module(f"power_openapi_models.{module_name}.models")
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj.__module__ == module.__name__
            ):
                registry[attr_name] = obj
    return registry


_REGISTRY = _build_registry()


def new_document(time_series_storage_file: str | None = "timeseries") -> SystemDocument:
    """Return a ready, empty ``SystemDocument``.

    ``trading_hub_associations`` and ``ext`` have defaults and could be left
    out, but they are passed explicitly so they survive ``write_document``'s
    ``exclude_unset`` and the document carries every association table -- which
    is what the Julia container emits, so the two languages agree.
    """
    return SystemDocument(
        components={},
        supplemental_attributes=[],
        supplemental_attribute_associations=[],
        plant_associations=[],
        combined_cycle_associations=[],
        service_associations=[],
        trading_hub_associations=[],
        time_series_associations=[],
        ext={},
        time_series_storage_file=time_series_storage_file,
    )


class CaseDocument:
    """Builder around a ``SystemDocument``: id minting, component bucketing,
    reference validation, and typed re-parse.
    """

    def __init__(self, time_series_storage_file: str | None = "timeseries") -> None:
        self.document = new_document(time_series_storage_file)
        self._next_id = 1

    def next_id(self) -> int:
        """Mint and return the next unused id. Ids start at 1 and are never
        reused.
        """
        value = self._next_id
        self._next_id += 1
        return value

    def add_component(self, model: BaseModel) -> int:
        """Bucket ``model`` by ``type(model).__name__`` and return its id.
        Assigns the id from the counter if the model's ``id`` is unset.

        Dumped with ``exclude_unset=True`` for the same reason the package's
        own ``write_document`` uses it: a field this build never set should
        stay absent, not be materialized as an explicit ``null`` (or, for a
        field with a nested default, as a whole default object). Julia's
        ``_encode`` skips absent fields, so without this the two languages
        emit different JSON for identical inputs -- Python carrying
        ``"dynamic_injector": null`` and a fully-populated ``curtailment_cost``
        that Julia omits entirely.

        It is ``exclude_unset``, not ``exclude_none``: a field this build
        deliberately set to ``None`` is a statement about the data and is kept.
        """
        id_value = getattr(model, "id", None)
        if id_value is None:
            id_value = self.next_id()
            model = model.model_copy(update={"id": id_value})
        else:
            self._next_id = max(self._next_id, id_value + 1)
        bucket = self.document.components.setdefault(type(model).__name__, [])
        bucket.append(model.model_dump(mode="json", by_alias=True, exclude_unset=True))
        return id_value

    def add_supplemental_attribute(
        self, model: BaseModel, *, component_id: int, component_type: str
    ) -> int:
        """Add a supplemental attribute describing one component. Mints the
        attribute's id, appends the dumped model to
        ``document.supplemental_attributes``, appends a matching
        ``SupplementalAttributeAssociation`` row, and returns the minted id.
        """
        id_value = getattr(model, "id", None)
        if id_value is None:
            id_value = self.next_id()
            model = model.model_copy(update={"id": id_value})
        else:
            self._next_id = max(self._next_id, id_value + 1)
        self.document.supplemental_attributes.append(
            model.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )
        self.document.supplemental_attribute_associations.append(
            SupplementalAttributeAssociation(
                component_id=component_id,
                component_type=component_type,
                attribute_id=id_value,
                attribute_type=type(model).__name__,
            )
        )
        return id_value

    def add_service_association(self, service_id: int, entity_id: int) -> None:
        """Append one ``ServiceAssociation`` row linking a service (e.g. an
        ``OnlineReserve``) to one contributing component.
        """
        self.document.service_associations.append(
            ServiceAssociation(service_id=service_id, entity_id=entity_id)
        )

    def validate(self) -> None:
        """Raise ``ValueError`` if any component id is duplicated, any known
        reference field points to an id that does not exist, or any
        ``service_associations`` row's ``service_id``/``entity_id`` does not
        resolve to a component id.
        """
        ids: set[int] = set()
        for type_name, items in self.document.components.items():
            for item in items:
                item_id = item.get("id")
                if item_id in ids:
                    raise ValueError(
                        f"duplicate id {item_id} on component {type_name}"
                    )
                ids.add(item_id)

        for type_name, items in self.document.components.items():
            for item in items:
                for field in _REFERENCE_FIELDS:
                    if field not in item:
                        continue
                    value = item[field]
                    if value is None or value in ids:
                        continue
                    raise ValueError(
                        f"unresolved reference: {type_name} id={item.get('id')} "
                        f"field {field!r} points to missing id {value}"
                    )

        for assoc in self.document.service_associations:
            if assoc.service_id not in ids:
                raise ValueError(
                    f"unresolved service association: service_id {assoc.service_id} "
                    f"does not resolve to a component id"
                )
            if assoc.entity_id not in ids:
                raise ValueError(
                    f"unresolved service association: entity_id {assoc.entity_id} "
                    f"does not resolve to a component id"
                )

    def typed_components(self) -> dict[str, list[BaseModel]]:
        """Re-parse the untyped ``components`` buckets into pydantic model
        instances, using a registry built from ``core``, ``operations``,
        ``timeseries``, ``infrastructure_core``, and ``investments``.
        """
        typed: dict[str, list[BaseModel]] = {}
        for type_name, items in self.document.components.items():
            model_cls = _REGISTRY.get(type_name)
            if model_cls is None:
                raise KeyError(
                    f"no registered model class for component type {type_name!r}"
                )
            typed[type_name] = [model_cls.model_validate(item) for item in items]
        return typed

    def write(self, path: str | Path) -> None:
        """Write the document to ``path`` via the package's ``write_document``."""
        write_document(self.document, path)

    @classmethod
    def read(cls, path: str | Path) -> "CaseDocument":
        """Read a document from ``path`` via the package's ``read_document``,
        restoring the id counter to one past the largest id seen.
        """
        instance = cls.__new__(cls)
        instance.document = read_document(path)
        max_id = 0
        for items in instance.document.components.values():
            for item in items:
                item_id = item.get("id")
                if isinstance(item_id, int) and item_id > max_id:
                    max_id = item_id
        instance._next_id = max_id + 1
        return instance


def new_portfolio_document(
    aggregation: str,
    *,
    base_system_file: str | None,
    time_series_storage_file: str | None = "timeseries",
) -> PortfolioDocument:
    """An empty ``PortfolioDocument`` with every required array present."""
    return PortfolioDocument(
        aggregation=aggregation,
        components={},
        supplemental_attributes=[],
        supplemental_attribute_associations=[],
        requirements_associations=[],
        time_series_associations=[],
        base_system_file=base_system_file,
        time_series_storage_file=time_series_storage_file,
    )


class PortfolioCase:
    """Builder around a ``PortfolioDocument``, the container an investments
    case belongs in.

    An investment portfolio is a *separate document* from the power system it
    expands — ``Investments/PortfolioDocument.json``, not
    ``Core/SystemDocument.json``. It has its own required keys
    (``aggregation``, ``requirements_associations``, ``base_system_file``) and
    a ``SystemDocument`` has nowhere to put them.

    The two documents share one id counter, because they cross-reference:
    a technology's ``region`` names an ``ACBus`` or ``Area`` id that lives in
    the *base system*, and ``requirements_associations`` rows name ids on
    both sides. Minting from one counter keeps every id in the pair unique, so
    a reference is unambiguous about which document it lands in.
    """

    def __init__(
        self,
        base: CaseDocument,
        *,
        aggregation: str,
        base_system_file: str | None,
        time_series_storage_file: str | None = "timeseries",
    ) -> None:
        self.base = base
        self.document = new_portfolio_document(
            aggregation,
            base_system_file=base_system_file,
            time_series_storage_file=time_series_storage_file,
        )

    def next_id(self) -> int:
        """Mint the next unused id from the *base system's* counter, so ids
        are unique across the document pair.
        """
        return self.base.next_id()

    def add_component(self, model: BaseModel) -> int:
        """Bucket ``model`` by ``type(model).__name__`` and return its id."""
        id_value = getattr(model, "id", None)
        if id_value is None:
            id_value = self.next_id()
            model = model.model_copy(update={"id": id_value})
        bucket = self.document.components.setdefault(type(model).__name__, [])
        bucket.append(model.model_dump(mode="json", by_alias=True, exclude_unset=True))
        return id_value

    def add_supplemental_attribute(
        self, model: BaseModel, *, component_id: int, component_type: str
    ) -> int:
        """Add a supplemental attribute describing one component, plus its
        ``SupplementalAttributeAssociation`` row. Returns the attribute's id.
        """
        id_value = getattr(model, "id", None)
        if id_value is None:
            id_value = self.next_id()
            model = model.model_copy(update={"id": id_value})
        self.document.supplemental_attributes.append(
            model.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )
        self.document.supplemental_attribute_associations.append(
            SupplementalAttributeAssociation(
                component_id=component_id,
                component_type=component_type,
                attribute_id=id_value,
                attribute_type=type(model).__name__,
            )
        )
        return id_value

    def add_requirement_association(self, *, requirement_id: int, entity_id: int) -> None:
        """Record that the policy requirement ``requirement_id`` applies to
        ``entity_id``.

        This replaces the ``requirements`` list an earlier version of this
        tutorial pushed onto the technology component itself. No release of
        SiennaSchemas has ever defined that field; the membership belongs in
        ``requirements_associations``, one row per (requirement, member) pair.

        Duplicate pairs are rejected rather than collapsed, matching
        ``PowerOpenAPIModels.jl``'s ``add_requirement_association!``.
        """
        pair = (requirement_id, entity_id)
        seen = {(row.requirement_id, row.entity_id) for row in self.document.requirements_associations}
        if pair in seen:
            raise ValueError(
                f"duplicate requirement membership: requirement_id={requirement_id} "
                f"entity_id={entity_id}"
            )
        self.document.requirements_associations.append(
            RequirementAssociation(requirement_id=requirement_id, entity_id=entity_id)
        )

    def validate(self) -> None:
        """Raise ``ValueError`` if any portfolio component id is duplicated or
        collides with a base-system id, or if any ``requirements_associations``
        row names an id that exists in neither document.
        """
        base_ids = {
            item.get("id")
            for items in self.base.document.components.values()
            for item in items
        }

        ids: set[int] = set()
        for type_name, items in self.document.components.items():
            for item in items:
                item_id = item.get("id")
                if item_id in ids or item_id in base_ids:
                    raise ValueError(f"duplicate id {item_id} on component {type_name}")
                ids.add(item_id)

        known = ids | base_ids
        for row in self.document.requirements_associations:
            if row.requirement_id not in known:
                raise ValueError(
                    f"unresolved requirement association: requirement_id "
                    f"{row.requirement_id} does not resolve to a component id"
                )
            if row.entity_id not in known:
                raise ValueError(
                    f"unresolved requirement association: entity_id {row.entity_id} "
                    f"does not resolve to a component id"
                )

    def typed_components(self) -> dict[str, list[BaseModel]]:
        """Re-parse the untyped ``components`` buckets into pydantic model
        instances, via the same registry ``CaseDocument`` uses.
        """
        typed: dict[str, list[BaseModel]] = {}
        for type_name, items in self.document.components.items():
            model_cls = _REGISTRY.get(type_name)
            if model_cls is None:
                raise KeyError(f"no registered model class for component type {type_name!r}")
            typed[type_name] = [model_cls.model_validate(item) for item in items]
        return typed

    def write(self, path: str | Path) -> None:
        """Write the portfolio to ``path`` via the package's
        ``write_portfolio_document``.
        """
        write_portfolio_document(self.document, path)

    @classmethod
    def read(cls, path: str | Path, base: CaseDocument) -> "PortfolioCase":
        """Read a portfolio from ``path``, against the ``base`` system it
        expands.
        """
        instance = cls.__new__(cls)
        instance.base = base
        instance.document = read_portfolio_document(path)
        return instance
