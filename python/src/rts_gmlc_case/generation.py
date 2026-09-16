"""Generator stage: all 158 units from ``SourceData/gen.csv`` and their
operating costs, plus the single ``EnergyReservoirStorage`` joined against
``SourceData/storage.csv``.

Mapping decisions (see CAMPAIGN-FACTS.md R4, R23, R26, R27 for the rulings
this follows):

- ``UNIT_TYPE_TO_MODEL`` has **12** entries, not 11 — ``ROR`` (run-of-river,
  one unit: ``201_HYDRO_4``) maps to ``HydroDispatch`` alongside ``HYDRO``
  (R4).
- ``time_limits`` is in **minutes**: the source ``Min Up/Down Time Hr``
  columns are hours and must be multiplied by 60 (R23). This applies to
  every family that carries the field (``ThermalStandard``,
  ``HydroDispatch``); it is a unit-system fact about the field, not a
  thermal-only quirk.
- ``rating`` is family-specific, not one formula (R26): ``ThermalStandard``
  and ``HydroDispatch`` use ``hypot(PMax MW, QMax MVAR)``; renewables use
  ``Base MVA`` (which coincides with ``PMax MW`` in every row);
  ``SynchronousCondenser`` uses ``QMax MVAR`` because its ``Base MVA`` is
  0.0 in the source, which is also why its ``base_power`` is the hardcoded
  ``SYNC_COND_BASE_POWER`` convention rather than a CSV column, and why it
  carries no ``prime_mover_type`` at all; ``EnergyReservoirStorage`` uses
  ``storage.csv``'s ``Rating MVA``.
- The thermal cost tree is deeply nested (R23): ``operation_cost`` ->
  ``variable_operation_cost`` (a ``FuelCurve``) -> ``value_curve`` (an
  ``INCREMENTAL`` curve) -> ``function_data`` (``PIECEWISE_STEP``). Built
  from plain nested dicts, matching the style ``branches.py`` already uses
  for RootModel-wrapped fields (e.g. the HVDC line's ``loss``), since
  pydantic validates those recursively regardless of the Python type of the
  literal passed in.
- ``storage.csv`` is not 1:1 with the one ``STORAGE``-typed generator: the
  single ``313_STORAGE_1`` row has a ``head`` and a ``tail`` entry with
  identical consumed fields (R7); the ``head`` row is used, for
  determinism. Its ``Storage Roundtrip Efficiency`` (85% in the source) is
  used directly, split evenly across the charge/discharge legs as
  ``sqrt(0.85)`` per leg — the reference case hardcodes ``1.0``/``1.0``
  instead, which is data loss this project does not repeat (R27).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from power_openapi_models.core.models import (
    EnergyUnitBasis,
    PrimeMovers,
    StorageTech,
    ThermalFuels,
    ThermalGenerationCost,
)
from power_openapi_models.infrastructure_core.models import InOut, MinMax, UnitSystem, UpDown
from power_openapi_models.operations.models import (
    CommitmentModes,
    EnergyReservoirStorage,
    HydroDispatch,
    OperationalStates,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
    ThermalStandard,
)

from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.topology import TopologyIndex

MINUTES_PER_HOUR = 60.0

# SynchronousCondenser's `Base MVA` is 0.0 for every row in gen.csv; 100.0 is
# a hardcoded convention, not a derived value (R26).
SYNC_COND_BASE_POWER = 100.0

UNIT_TYPE_TO_MODEL: dict[str, str] = {
    "NUCLEAR": "ThermalStandard",
    "STEAM": "ThermalStandard",
    "CT": "ThermalStandard",
    "CC": "ThermalStandard",
    "WIND": "RenewableDispatch",
    "PV": "RenewableDispatch",
    "CSP": "RenewableDispatch",
    "RTPV": "RenewableNonDispatch",
    "HYDRO": "HydroDispatch",
    "ROR": "HydroDispatch",
    "SYNC_COND": "SynchronousCondenser",
    "STORAGE": "EnergyReservoirStorage",
}

PRIME_MOVER_BY_UNIT_TYPE: dict[str, PrimeMovers] = {
    "PV": PrimeMovers.PVe,
    "RTPV": PrimeMovers.PVe,
    "WIND": PrimeMovers.WT,
    "CSP": PrimeMovers.CP,
    "HYDRO": PrimeMovers.HY,
    "ROR": PrimeMovers.HY,
    "STORAGE": PrimeMovers.BA,
    "NUCLEAR": PrimeMovers.ST,
    "STEAM": PrimeMovers.ST,
    "CT": PrimeMovers.CT,
    "CC": PrimeMovers.CC,
    # SYNC_COND has no prime_mover_type field on SynchronousCondenser.
}

FUEL_BY_SOURCE: dict[str, ThermalFuels] = {
    "Oil": ThermalFuels.DISTILLATE_FUEL_OIL,
    "Coal": ThermalFuels.COAL,
    "NG": ThermalFuels.NATURAL_GAS,
    "Nuclear": ThermalFuels.NUCLEAR,
}


def unit_type_target(unit_type: str) -> str:
    """Return the target component type name for a gen.csv ``Unit Type``.

    Raises ``ValueError`` if ``unit_type`` is not in ``UNIT_TYPE_TO_MODEL``.
    """
    target = UNIT_TYPE_TO_MODEL.get(unit_type)
    if target is None:
        raise ValueError(f"unmapped Unit Type {unit_type!r}")
    return target


def thermal_cost(row: dict) -> ThermalGenerationCost:
    """Build the nested ``THERMAL`` operation cost for one gen.csv row.

    Verified against ``101_CT_1`` (CAMPAIGN-FACTS.md thermal-cost table):
    ``x_coords[k] = Output_pct_k * PMax MW`` for the nonempty blocks,
    ``y_coords[k] = HR_incr_k`` for ``k >= 1``, ``initial_input = HR_avg_0 *
    x_coords[0]`` (no x1000 factor), ``fuel_cost = Fuel Price / 1000``, and
    ``start_up = Non Fuel Start Cost $ + Start Heat Cold MBTU * Fuel Price``.
    """
    pmax = float(row["PMax MW"])
    x_coords = [
        float(row[f"Output_pct_{k}"]) * pmax
        for k in range(5)
        if not pd.isna(row[f"Output_pct_{k}"])
    ]
    y_coords = [
        float(row[f"HR_incr_{k}"])
        for k in range(1, 5)
        if not pd.isna(row[f"HR_incr_{k}"])
    ]
    fuel_price = float(row["Fuel Price $/MMBTU"])
    return ThermalGenerationCost(
        # The discriminator is passed explicitly, never left to its default: the document
        # omits fields this build never set, and a consumer needs `cost_type` to pick the
        # variant. Every sibling cost below does the same.
        cost_type="THERMAL",
        fixed=0.0,
        shut_down=float(row["Non Fuel Shutdown Cost $"]),
        start_up=float(row["Non Fuel Start Cost $"]) + float(row["Start Heat Cold MBTU"]) * fuel_price,
        variable_operation_cost={
            "fuel_cost": fuel_price / 1000.0,
            "power_units": "NATURAL_UNITS",
            "variable_cost_type": "FUEL",
            "value_curve": {
                "curve_type": "INCREMENTAL",
                "function_data": {
                    "function_type": "PIECEWISE_STEP",
                    "x_coords": x_coords,
                    "y_coords": y_coords,
                },
                "initial_input": float(row["HR_avg_0"]) * x_coords[0],
            },
            "vom_cost": {
                "curve_type": "INPUT_OUTPUT",
                "function_data": {
                    "function_type": "LINEAR",
                    "constant_term": 0.0,
                    "proportional_term": float(row["VOM"]),
                },
            },
        },
    )


def _build_thermal_standard(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> ThermalStandard:
    uid = str(row["GEN UID"])
    unit_type = str(row["Unit Type"])
    fuel_name = str(row["Fuel"])
    fuel = FUEL_BY_SOURCE.get(fuel_name)
    if fuel is None:
        raise ValueError(f"gen.csv row {uid!r}: unmapped Fuel {fuel_name!r}")

    ramp = float(row["Ramp Rate MW/Min"])
    return ThermalStandard(
        id=doc.next_id(),
        name=uid,
        available=True,
        # RTS carries no initial-commitment state, so "all units online at
        # t0" is a tutorial convention, not source data. ThermalStandard
        # *requires* this field in Python (OperationalStates enum) while the
        # Julia package currently leaves it optional/untyped, so the value
        # is pinned deliberately to keep both languages' output identical.
        status=OperationalStates.ONLINE,
        # MARKET was removed upstream; COMMITTED is the field's own default
        # and the closest analogue for an online, dispatchable thermal unit.
        commitment_mode=CommitmentModes.COMMITTED,
        bus=bus_id,
        active_power=float(row["MW Inj"]),
        reactive_power=float(row["MVAR Inj"]),
        rating=math.hypot(float(row["PMax MW"]), float(row["QMax MVAR"])),
        active_power_limits=MinMax(min=float(row["PMin MW"]), max=float(row["PMax MW"])),
        reactive_power_limits=MinMax(min=float(row["QMin MVAR"]), max=float(row["QMax MVAR"])),
        ramp_limits=UpDown(up=ramp, down=ramp),
        operation_cost=thermal_cost(row),
        base_power=float(row["Base MVA"]),
        power_units=UnitSystem.NATURAL_UNITS,
        time_limits=UpDown(
            up=float(row["Min Up Time Hr"]) * MINUTES_PER_HOUR,
            down=float(row["Min Down Time Hr"]) * MINUTES_PER_HOUR,
        ),
        must_run=False,
        prime_mover_type=PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        fuel=fuel,
        time_at_status=600000.0,
    )


def _build_renewable_dispatch(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> RenewableDispatch:
    unit_type = str(row["Unit Type"])
    base_power = float(row["Base MVA"])
    return RenewableDispatch(
        id=doc.next_id(),
        name=str(row["GEN UID"]),
        available=True,
        bus=bus_id,
        active_power=float(row["MW Inj"]),
        reactive_power=float(row["MVAR Inj"]),
        rating=base_power,
        prime_mover_type=PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        reactive_power_limits=MinMax(min=float(row["QMin MVAR"]), max=float(row["QMax MVAR"])),
        power_factor=1.0,
        operation_cost={
            "cost_type": "RENEWABLE",
            "fixed": 0.0,
            "variable_operation_cost": {
                "power_units": "NATURAL_UNITS",
                "variable_cost_type": "COST",
                "value_curve": {
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "constant_term": 0.0,
                        "proportional_term": 0.0,
                    },
                },
                "vom_cost": {
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "constant_term": 0.0,
                        "proportional_term": float(row["VOM"]),
                    },
                },
            },
        },
        base_power=base_power,
        power_units=UnitSystem.NATURAL_UNITS,
    )


def _build_renewable_non_dispatch(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> RenewableNonDispatch:
    base_power = float(row["Base MVA"])
    return RenewableNonDispatch(
        id=doc.next_id(),
        name=str(row["GEN UID"]),
        available=True,
        bus=bus_id,
        active_power=float(row["MW Inj"]),
        reactive_power=float(row["MVAR Inj"]),
        rating=base_power,
        prime_mover_type=PrimeMovers.PVe,
        power_factor=1.0,
        base_power=base_power,
        power_units=UnitSystem.NATURAL_UNITS,
    )


def _build_hydro_dispatch(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> HydroDispatch:
    unit_type = str(row["Unit Type"])
    ramp = float(row["Ramp Rate MW/Min"])
    return HydroDispatch(
        id=doc.next_id(),
        name=str(row["GEN UID"]),
        available=True,
        bus=bus_id,
        active_power=float(row["MW Inj"]),
        reactive_power=float(row["MVAR Inj"]),
        rating=math.hypot(float(row["PMax MW"]), float(row["QMax MVAR"])),
        prime_mover_type=PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        active_power_limits=MinMax(min=float(row["PMin MW"]), max=float(row["PMax MW"])),
        reactive_power_limits=MinMax(min=float(row["QMin MVAR"]), max=float(row["QMax MVAR"])),
        ramp_limits=UpDown(up=ramp, down=ramp),
        time_limits=UpDown(
            up=float(row["Min Up Time Hr"]) * MINUTES_PER_HOUR,
            down=float(row["Min Down Time Hr"]) * MINUTES_PER_HOUR,
        ),
        base_power=float(row["Base MVA"]),
        power_units=UnitSystem.NATURAL_UNITS,
        status=OperationalStates.ONLINE,
        time_at_status=600000.0,
        operation_cost={
            "cost_type": "HYDRO_GEN",
            "fixed": 0.0,
            "variable_operation_cost": {
                # Same FuelCurve.fuel_cost units as thermal_cost()'s
                # fuel_cost above ($/MMBTU -> $/thousand-BTU): both paths
                # feed the same FuelCurve type and must stay in step. This
                # is invisible today only because every hydro/ROR row has
                # Fuel Price == 0.0.
                "fuel_cost": float(row["Fuel Price $/MMBTU"]) / 1000.0,
                "power_units": "NATURAL_UNITS",
                "variable_cost_type": "FUEL",
                # INPUT_OUTPUT (not AVERAGE_RATE) confirmed against the
                # reference case: every HydroDispatch/HydroTurbine there
                # uses curve_type INPUT_OUTPUT with a LINEAR proportional
                # term of HR_avg_0. AVERAGE_RATE was considered (HR_avg_0 is
                # literally an average heat rate) and rejected to match.
                "value_curve": {
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "constant_term": 0.0,
                        "proportional_term": float(row["HR_avg_0"]),
                    },
                },
                "vom_cost": {
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "constant_term": 0.0,
                        "proportional_term": float(row["VOM"]),
                    },
                },
            },
        },
    )


def _build_synchronous_condenser(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> SynchronousCondenser:
    return SynchronousCondenser(
        id=doc.next_id(),
        name=str(row["GEN UID"]),
        available=True,
        bus=bus_id,
        reactive_power=float(row["MVAR Inj"]),
        rating=float(row["QMax MVAR"]),
        reactive_power_limits=MinMax(min=float(row["QMin MVAR"]), max=float(row["QMax MVAR"])),
        base_power=SYNC_COND_BASE_POWER,
        power_units=UnitSystem.NATURAL_UNITS,
        active_power_losses=0.0,
    )


def _build_energy_reservoir_storage(
    doc: CaseDocument, row: dict, bus_id: int, storage_row: dict | None
) -> EnergyReservoirStorage:
    uid = str(row["GEN UID"])
    if storage_row is None:
        raise ValueError(f"gen.csv row {uid!r}: Unit Type STORAGE has no storage.csv row")

    rating = float(storage_row["Rating MVA"])
    max_volume_gwh = float(storage_row["Max Volume GWh"])
    pump_load = float(row["Pump Load MW"])
    # 85% roundtrip in the source, split evenly across the two legs (R27) —
    # the reference case hardcodes 1.0/1.0 instead, discarding this figure.
    leg_efficiency = math.sqrt(float(row["Storage Roundtrip Efficiency"]) / 100.0)

    return EnergyReservoirStorage(
        id=doc.next_id(),
        name=uid,
        available=True,
        bus=bus_id,
        prime_mover_type=PrimeMovers.BA,
        storage_technology_type=StorageTech.OTHER_CHEM,
        storage_capacity=max_volume_gwh * 1000.0,
        energy_units=EnergyUnitBasis.MWH,
        storage_level_limits=MinMax(min=0.0, max=1.0),
        initial_storage_capacity_level=float(storage_row["Initial Volume GWh"]) / max_volume_gwh,
        rating=rating,
        active_power=0.0,
        # The single storage row can't disambiguate this from `2 * Base MVA`
        # -- both give 100.0 here. `Pump Load MW` is chosen as the more
        # semantically apt source (it's literally the charging capacity).
        input_active_power_limits=MinMax(min=0.0, max=2.0 * pump_load),
        output_active_power_limits=MinMax(min=0.0, max=rating),
        efficiency=InOut(**{"in": leg_efficiency, "out": leg_efficiency}),
        reactive_power=0.0,
        base_power=float(row["Base MVA"]),
        power_units=UnitSystem.NATURAL_UNITS,
        conversion_factor=1.0,
        storage_target=0.0,
        cycle_limits=10000,
        self_discharge=0.0,
        standing_loss=0.0,
        operation_cost={
            "cost_type": "STORAGE",
            "fixed": 0.0,
            "shut_down": 0.0,
            "start_up": 0.0,
            "energy_shortage_cost": 0.0,
            "energy_surplus_cost": 0.0,
        },
    )


_BUILDERS: dict[str, Callable[[CaseDocument, dict, int, dict | None], BaseModel]] = {
    "ThermalStandard": _build_thermal_standard,
    "RenewableDispatch": _build_renewable_dispatch,
    "RenewableNonDispatch": _build_renewable_non_dispatch,
    "HydroDispatch": _build_hydro_dispatch,
    "SynchronousCondenser": _build_synchronous_condenser,
    "EnergyReservoirStorage": _build_energy_reservoir_storage,
}


def _storage_head_rows(source: Path) -> dict[str, dict]:
    """Return ``storage.csv``'s ``position == "head"`` row per ``GEN UID``.

    ``storage.csv`` is not 1:1 with generators (R7): most rows belong to
    HYDRO/CSP generators this module never looks up, and the one row that
    matters here (``313_STORAGE_1``) has both a ``head`` and a ``tail``
    entry with identical consumed fields — ``head`` is used for
    determinism.
    """
    storage = pd.read_csv(source / "storage.csv")
    head_rows: dict[str, dict] = {}
    for uid, group in storage.groupby("GEN UID"):
        head = group[group["position"] == "head"]
        if not head.empty:
            head_rows[str(uid)] = head.iloc[0].to_dict()
    return head_rows


def add_generation(doc: CaseDocument, source: Path, idx: TopologyIndex) -> dict[str, int]:
    """Add every generator in ``source/gen.csv`` to ``doc``, dispatching to
    one builder per target component type (``UNIT_TYPE_TO_MODEL``). Returns
    a mapping from ``GEN UID`` to the minted component id, iterated in file
    order.
    """
    gen = pd.read_csv(source / "gen.csv")
    storage_head_by_uid = _storage_head_rows(source)

    generator_id_by_uid: dict[str, int] = {}
    for row in gen.to_dict("records"):
        uid = str(row["GEN UID"])
        unit_type = str(row["Unit Type"])
        try:
            target = unit_type_target(unit_type)
        except ValueError as exc:
            raise ValueError(f"gen.csv row {uid!r}: {exc}") from exc

        bus_number = int(row["Bus ID"])
        if bus_number not in idx.bus_id_by_number:
            raise ValueError(f"gen.csv row {uid!r}: unmapped bus {bus_number!r}")
        bus_id = idx.bus_id_by_number[bus_number]

        builder = _BUILDERS[target]
        component = builder(doc, row, bus_id, storage_head_by_uid.get(uid))
        generator_id_by_uid[uid] = doc.add_component(component)

    return generator_id_by_uid
