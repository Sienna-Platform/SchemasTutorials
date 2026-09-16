"""Branch stage: arcs, lines, transformers, and the single HVDC line, from
``SourceData/branch.csv`` and ``SourceData/dc_branch.csv``.

Mapping decisions (see CAMPAIGN-FACTS.md R21, R22 for the rulings this
follows):

- A branch is a transformer when its two buses have different base
  voltages — physical, self-documenting, and equivalent to
  ``Tr Ratio not in {0.0, 1.0}``. Branch ``C35`` (230 kV -> 230 kV,
  ``Tr Ratio`` exactly 1.0) is an identity element, not a transformer, and
  the plan's naive ``Tr Ratio != 0`` rule misclassifies it. Both
  formulations must agree; ``add_branches`` raises loudly if they ever
  disagree for a row.
- Every transformer becomes a ``TransformerCircuit`` (the electrical
  parameters; no ``name``) plus a ``TwoWindingTransformer`` (the named
  component, referencing the circuit by id).
- One ``Arc`` per distinct ordered ``(from_id, to_id)`` pair, shared across
  ``branch.csv`` and ``dc_branch.csv``.
- Every component sets ``power_units=NATURAL_UNITS`` and an explicit
  ``base_power``; branch components also set
  ``parameter_units=COMPONENT_BASE`` (and ``TwoWindingTransformer`` sets
  ``admittance_units=COMPONENT_BASE``) so per-unit impedances coexist with a
  natural-units case.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from power_openapi_models.core.models import (
    AdmittanceUnitBasis,
    Arc,
    ImpedanceUnitBasis,
    LossCurve,
)
from power_openapi_models.infrastructure_core.models import (
    ComplexNumber,
    FromTo,
    MinMax,
    UnitSystem,
)
from power_openapi_models.operations.models import (
    Line,
    TransformerCircuit,
    TransformerControlObjective,
    TwoTerminalGenericHVDCLine,
    TwoWindingTransformer,
    TwoWindingTransformerShuntLocation,
)

from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import TopologyIndex

BASE_POWER = 100.0
ANGLE_LIMITS = MinMax(min=-3.1416, max=3.1416)
CONTROL_LIMITS = MinMax(min=0.9, max=1.1)
CONTROLLED_QUANTITY_LIMITS = MinMax(min=1.0, max=1.0)
NUMBER_OF_TAP_POSITIONS = 33


def _arc_id(
    doc: CaseDocument,
    idx: TopologyIndex,
    cache: dict[tuple[int, int], int],
    from_bus_number: int,
    to_bus_number: int,
) -> int:
    """Return the id of the ``Arc`` for ``(from_bus_number, to_bus_number)``,
    minting a fresh one the first time this ordered pair is seen and reusing
    it thereafter.
    """
    if from_bus_number not in idx.bus_id_by_number:
        raise ValueError(f"unmapped from-bus {from_bus_number!r}: not in topology index")
    if to_bus_number not in idx.bus_id_by_number:
        raise ValueError(f"unmapped to-bus {to_bus_number!r}: not in topology index")
    from_id = idx.bus_id_by_number[from_bus_number]
    to_id = idx.bus_id_by_number[to_bus_number]
    key = (from_id, to_id)
    if key in cache:
        return cache[key]
    arc = Arc(id=doc.next_id(), from_id=from_id, to_id=to_id)
    arc_id = doc.add_component(arc)
    cache[key] = arc_id
    return arc_id


def add_branches(doc: CaseDocument, source: Path, idx: TopologyIndex) -> None:
    """Add ``Arc``, ``Line``, ``TransformerCircuit``, ``TwoWindingTransformer``,
    and ``TwoTerminalGenericHVDCLine`` components from ``source/branch.csv``
    and ``source/dc_branch.csv`` to ``doc``.
    """
    bus = pd.read_csv(source / "bus.csv")
    base_kv_by_number: dict[int, float] = dict(zip(bus["Bus ID"], bus["BaseKV"]))

    arc_cache: dict[tuple[int, int], int] = {}

    branch = pd.read_csv(source / "branch.csv")
    for row in branch.to_dict("records"):
        uid = str(row["UID"])
        from_bus = int(row["From Bus"])
        to_bus = int(row["To Bus"])

        if from_bus not in base_kv_by_number:
            raise ValueError(f"branch {uid}: unmapped from-bus {from_bus!r} in bus.csv")
        if to_bus not in base_kv_by_number:
            raise ValueError(f"branch {uid}: unmapped to-bus {to_bus!r} in bus.csv")
        from_kv = float(base_kv_by_number[from_bus])
        to_kv = float(base_kv_by_number[to_bus])
        tr_ratio = float(row["Tr Ratio"])

        is_transformer = from_kv != to_kv
        tr_ratio_says_transformer = tr_ratio not in (0.0, 1.0)
        if is_transformer != tr_ratio_says_transformer:
            raise ValueError(
                f"branch {uid}: voltage-based classification ({is_transformer}) "
                f"disagrees with the Tr Ratio rule ({tr_ratio_says_transformer}) "
                f"-- from_kv={from_kv}, to_kv={to_kv}, tr_ratio={tr_ratio}"
            )

        arc = _arc_id(doc, idx, arc_cache, from_bus, to_bus)
        rating = float(row["Cont Rating"])
        rating_b = float(row["LTE Rating"])
        rating_c = float(row["STE Rating"])

        if is_transformer:
            circuit = TransformerCircuit(
                id=doc.next_id(),
                available=True,
                arc=arc,
                tap=tr_ratio,
                alpha=0.0,
                parameter_units=ImpedanceUnitBasis.COMPONENT_BASE,
                r=float(row["R"]),
                x=float(row["X"]),
                control_objective=TransformerControlObjective.FIXED,
                control_limits=CONTROL_LIMITS,
                controlled_quantity_limits=CONTROLLED_QUANTITY_LIMITS,
                regulated_bus_number=0,
                number_of_tap_positions=NUMBER_OF_TAP_POSITIONS,
                rating=rating,
                rating_b=rating_b,
                rating_c=rating_c,
                active_power_flow=0.0,
                reactive_power_flow=0.0,
                base_power=BASE_POWER,
                power_units=UnitSystem.NATURAL_UNITS,
                base_voltage_primary=from_kv,
                base_voltage_secondary=to_kv,
            )
            circuit_id = doc.add_component(circuit)

            transformer = TwoWindingTransformer(
                id=doc.next_id(),
                name=uid,
                circuit=circuit_id,
                magnetizing_shunt=ComplexNumber(real=0.0, imag=0.0),
                shunt_location=TwoWindingTransformerShuntLocation.PRIMARY,
                admittance_units=AdmittanceUnitBasis.COMPONENT_BASE,
            )
            doc.add_component(transformer)
        else:
            b_half = float(row["B"]) / 2.0
            line = Line(
                id=doc.next_id(),
                name=uid,
                available=True,
                active_power_flow=0.0,
                reactive_power_flow=0.0,
                arc=arc,
                r=float(row["R"]),
                x=float(row["X"]),
                base_power=BASE_POWER,
                power_units=UnitSystem.NATURAL_UNITS,
                parameter_units=ImpedanceUnitBasis.COMPONENT_BASE,
                b=FromTo(**{"from": b_half, "to": b_half}),
                rating=rating,
                rating_b=rating_b,
                rating_c=rating_c,
                angle_limits=ANGLE_LIMITS,
                g=FromTo(**{"from": 0.0, "to": 0.0}),
            )
            doc.add_component(line)

    dc_branch = pd.read_csv(source / "dc_branch.csv")
    for row in dc_branch.to_dict("records"):
        uid = str(row["UID"])
        from_bus = int(row["From Bus"])
        to_bus = int(row["To Bus"])
        arc = _arc_id(doc, idx, arc_cache, from_bus, to_bus)
        mw_load = float(row["MW Load"])
        margin = float(row["Margin"])

        hvdc = TwoTerminalGenericHVDCLine(
            id=doc.next_id(),
            name=uid,
            available=True,
            active_power_flow=0.0,
            arc=arc,
            active_power_limits_from=MinMax(min=-mw_load, max=mw_load),
            active_power_limits_to=MinMax(min=-mw_load, max=mw_load),
            reactive_power_limits_from=MinMax(min=0.0, max=100.0),
            reactive_power_limits_to=MinMax(min=0.0, max=100.0),
            loss=LossCurve(
                power_units=UnitSystem.NATURAL_UNITS,
                value_curve={
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "constant_term": 0.0,
                        "proportional_term": margin,
                    },
                },
            ),
            base_power=BASE_POWER,
            power_units=UnitSystem.NATURAL_UNITS,
        )
        doc.add_component(hvdc)
