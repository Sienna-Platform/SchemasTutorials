"""Time-series stage: reads the 282 ``timeseries_pointers.csv`` rows, writes
each pointer's profile through the parquet sidecar, and attaches one
``SingleTimeSeries`` association per pointer to the document.

Mapping decisions (see CAMPAIGN-FACTS.md R5, R6, R20, R32, R33 for the
rulings this follows):

- Two CSV layouts, detected by whether a ``Period`` column is present
  (R20): **Layout A** has ``Year,Month,Day,Period,<object1>,<object2>,...``
  with ``Period`` resetting every day, and the pointer's ``Object`` selects
  the column. **Layout B** has ``Year,Month,Day,1,2,...,24`` (or
  ``...,288``), one row per day and no object column — the whole file is
  one series, flattened row-major (day by day, period ascending) to the
  same shape Layout A yields. Every generator directory and ``Load/`` use
  Layout A throughout. ``Reserves/`` is mixed, not uniformly Layout B as
  R20 states: ``Spin_Up_R1``/``R2``/``R3`` are Layout A (one object column
  named after the product), ``Flex_*``/``Reg_*`` are Layout B — the
  Period-column detection handles both without special-casing the
  directory, and the reserve product name is a valid column selector
  either way (Layout B ignores it).
- ``Parameter`` maps to the association's ``name`` (not ``component_field``,
  which stays unset) and a ``quantity_kind``: ``PMax MW``/``MW Load`` ->
  ``max_active_power``, ``PMin MW`` -> ``min_active_power`` (both
  ``active_power``); ``Requirement`` -> ``requirement`` (``active_power``);
  ``Natural_Inflow`` -> ``inflow`` (``power``).
- Owner resolution: ``Category == "Generator"`` -> the generator id by
  ``Object``, except the two ``Natural_Inflow`` rows whose ``Object`` is a
  ``storage.csv`` ``Storage`` name (``212_CSP_HEAD_STORAGE``), resolved
  through ``Storage`` -> ``GEN UID`` (R6) — the resolved ``GEN UID`` doubles
  as the profile's column name, since that is what the source CSV's header
  actually spells. ``Category`` in ``("Area", "Region", "Zone")`` -> the
  ``Area`` by name. ``Category == "Reserve"`` -> the reserve id.
- ``resolution`` is ``PT1H`` for ``DAY_AHEAD`` and ``PT5M`` for
  ``REAL_TIME`` (R32 reverses the plan's ``PT3600S``/``PT300S``).
  ``element_type`` is the pinned literal ``"f64"`` (R17). ``time_reference``
  is ``"zoneless"`` on every record. ``unit_system="NATURAL_UNITS"`` and
  ``units="MW"`` are deliberate divergences from the reference (which
  stores per-unit profiles); our sidecar's ``uri`` is a parquet path, not
  the reference's bare HDF5 hash.
- The 102 ``PMin MW`` series are byte-identical to their ``PMax MW``
  partners (R33): because the sidecar is content-addressed, they collapse
  to the same parquet file, giving a strong end-to-end dedup check.
- ``Data File`` paths are resolved case-insensitively
  (``resolve_case_insensitive_path``): the source data itself disagrees
  with its own directory casing (``HYDRO`` referenced, ``Hydro`` on disk —
  80 of 282 pointers) and, in one place, filename casing
  (``REAL_TIME_regional_load.csv`` referenced,
  ``REAL_TIME_regional_Load.csv`` on disk). Both resolve silently on
  macOS's case-insensitive filesystem and would raise
  ``FileNotFoundError`` on Linux; this is fixed in code rather than
  relying on the filesystem to hide it (Fix round 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from power_openapi_models.timeseries.models import (
    OwnerCategory,
    SingleTimeSeries,
    TimeSeriesAssociation,
)

from rts_gmlc_case.document import CaseDocument
from rts_gmlc_case.generation import unit_type_target
from rts_gmlc_case.sidecar import SidecarWriter

TIME_SERIES_STORAGE_FILE = "timeseries"

# Simulation -> (resolution string, per-step Timedelta). R32 pins PT1H/PT5M,
# reversing the task plans' PT3600S/PT300S.
RESOLUTION_BY_SIMULATION: dict[str, tuple[str, pd.Timedelta]] = {
    "DAY_AHEAD": ("PT1H", pd.Timedelta(hours=1)),
    "REAL_TIME": ("PT5M", pd.Timedelta(minutes=5)),
}


@dataclass(frozen=True)
class _Target:
    """One ``Parameter`` value's association ``name`` and ``quantity_kind``."""

    name: str
    quantity_kind: str


# R5's five-entry Parameter map, plus each target's quantity_kind (verified
# against the reference case's coverage table, CAMPAIGN-FACTS.md's
# reference-fields.md). Literal `"Requirement (MW)"` never appears in the
# data -- the real value is `Requirement`.
PARAMETER_TARGETS: dict[str, _Target] = {
    "PMax MW": _Target("max_active_power", "active_power"),
    "PMin MW": _Target("min_active_power", "active_power"),
    "MW Load": _Target("max_active_power", "active_power"),
    "Requirement": _Target("requirement", "active_power"),
    "Natural_Inflow": _Target("inflow", "power"),
}


@dataclass
class TimeSeriesOwners:
    """The id maps time-series pointers resolve owners against, bundled from
    the earlier stages' return values.
    """

    generator_id_by_uid: dict[str, int]
    area_id_by_name: dict[str, int]
    reserve_id_by_product: dict[str, int]


@lru_cache(maxsize=None)
def _load_csv(csv_path: str) -> pd.DataFrame:
    """Cache raw CSV reads: many pointer rows share one underlying data file
    (e.g. every WIND object shares one file), and some REAL_TIME files run
    to 100k+ rows, so re-reading per pointer is wasteful.
    """
    return pd.read_csv(csv_path)


def _layout_a_timestamps(df: pd.DataFrame, resolution: pd.Timedelta) -> pd.DatetimeIndex:
    dates = pd.to_datetime({"year": df["Year"], "month": df["Month"], "day": df["Day"]})
    step = np.timedelta64(resolution)
    offsets = (df["Period"].to_numpy() - 1) * step
    return pd.DatetimeIndex(dates.to_numpy() + offsets).tz_localize("UTC")


def _read_layout_a(
    df: pd.DataFrame, column: str | None, resolution: pd.Timedelta
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    if column is None:
        raise ValueError("Layout A (a Period column is present) requires a column name")
    if column not in df.columns:
        raise ValueError(
            f"column {column!r} not found; available columns: {list(df.columns)}"
        )
    timestamps = _layout_a_timestamps(df, resolution)
    values = df[column].to_numpy(dtype="float64")
    return timestamps, values


def _read_layout_b(
    df: pd.DataFrame, resolution: pd.Timedelta
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    period_columns = [c for c in df.columns if c not in ("Year", "Month", "Day")]
    dates = pd.to_datetime(
        {"year": df["Year"], "month": df["Month"], "day": df["Day"]}
    ).to_numpy()
    step = np.timedelta64(resolution)
    offsets = np.arange(len(period_columns)) * step
    # Row-major flatten: day by day, period ascending within each day.
    grid = dates.reshape(-1, 1) + offsets.reshape(1, -1)
    timestamps = pd.DatetimeIndex(grid.reshape(-1)).tz_localize("UTC")
    values = df[period_columns].to_numpy(dtype="float64").reshape(-1)
    return timestamps, values


def resolve_case_insensitive_path(base: Path, relative: str) -> Path:
    """Resolve ``relative`` (e.g. ``"../timeseries_data_files/HYDRO/x.csv"``)
    against ``base``'s actual on-disk entries, one path component at a
    time, falling back to a case-insensitive match when no exact-case entry
    exists.

    RTS-GMLC's own ``timeseries_pointers.csv`` disagrees with the source
    tree's real casing in two places (verified against every referenced
    path): the ``HYDRO`` directory is really ``Hydro`` on disk (80 of 282
    pointers), and ``Load/REAL_TIME_regional_load.csv`` is really
    ``REAL_TIME_regional_Load.csv``. Both resolve silently on a
    case-insensitive filesystem (macOS default) and raise
    ``FileNotFoundError`` on a case-sensitive one (Linux, most CI) — this
    function makes the lookup case-insensitive deliberately, rather than
    relying on the filesystem to paper over the mismatch.

    Raises ``ValueError`` (naming the component and ``relative``) if a
    component has zero or more than one case-insensitive match — never
    falls back silently on an ambiguous or missing entry.
    """
    current = base
    for part in Path(relative).parts:
        if part in ("..", "."):
            current = current.parent if part == ".." else current
            continue
        try:
            entries = [entry.name for entry in current.iterdir()]
        except FileNotFoundError as exc:
            raise ValueError(
                f"cannot resolve {relative!r} against {base}: "
                f"{current} does not exist"
            ) from exc
        if part in entries:
            current = current / part
            continue
        matches = [entry for entry in entries if entry.lower() == part.lower()]
        if len(matches) == 1:
            current = current / matches[0]
        elif len(matches) == 0:
            raise ValueError(
                f"cannot resolve {relative!r} against {base}: no entry named "
                f"{part!r} (case-insensitively) in {current}"
            )
        else:
            raise ValueError(
                f"cannot resolve {relative!r} against {base}: ambiguous "
                f"case-insensitive match for {part!r} in {current}: {matches}"
            )
    return current


def read_profile(
    csv_path: Path, column: str | None, resolution: pd.Timedelta
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Read one RTS time-series data file, dispatching on layout (R20).

    Layout A (``Year,Month,Day,Period,<object1>,...``) selects ``column``;
    Layout B (``Year,Month,Day,1,2,...``, some ``Reserves/`` files) ignores
    ``column`` and flattens the whole file row-major. Detected by whether a
    ``Period`` column is present. Both paths return the same
    ``(timestamps, values)`` shape.
    """
    df = _load_csv(str(csv_path))
    if "Period" in df.columns:
        return _read_layout_a(df, column, resolution)
    return _read_layout_b(df, resolution)


def _resolve_generator_object(
    obj: str,
    generator_id_by_uid: dict[str, int],
    storage_gen_uid_by_storage_name: dict[str, str],
) -> str:
    """Return the ``GEN UID`` a Generator-category pointer's ``Object``
    resolves to -- itself if it already is one, else its owner via
    ``storage.csv``'s ``Storage`` -> ``GEN UID`` column (R6). The resolved
    ``GEN UID`` also names the profile's data column.
    """
    if obj in generator_id_by_uid:
        return obj
    resolved = storage_gen_uid_by_storage_name.get(obj)
    if resolved is not None and resolved in generator_id_by_uid:
        return resolved
    raise ValueError(
        f"Generator Object {obj!r} resolves through neither GEN UID nor "
        "storage.csv's Storage -> GEN UID map"
    )


def attach_time_series(
    doc: CaseDocument,
    source: Path,
    sidecar: SidecarWriter,
    owners: TimeSeriesOwners,
) -> None:
    """Attach one ``SingleTimeSeries`` association per
    ``source/timeseries_pointers.csv`` row, writing each profile through
    ``sidecar`` first. Raises ``ValueError`` (naming the row) on any
    unmapped ``Simulation``, ``Category``, ``Parameter``, or unresolvable
    owner.
    """
    doc.document.time_series_storage_file = TIME_SERIES_STORAGE_FILE

    pointers = pd.read_csv(source / "timeseries_pointers.csv")
    storage = pd.read_csv(source / "storage.csv")
    storage_gen_uid_by_storage_name = dict(zip(storage["Storage"], storage["GEN UID"]))
    gen = pd.read_csv(source / "gen.csv")
    unit_type_by_uid = dict(zip(gen["GEN UID"].astype(str), gen["Unit Type"].astype(str)))

    for row in pointers.to_dict("records"):
        simulation = str(row["Simulation"])
        resolution_pair = RESOLUTION_BY_SIMULATION.get(simulation)
        if resolution_pair is None:
            raise ValueError(f"timeseries_pointers.csv row {row}: unmapped Simulation {simulation!r}")
        resolution_str, resolution_delta = resolution_pair

        parameter = str(row["Parameter"])
        target = PARAMETER_TARGETS.get(parameter)
        if target is None:
            raise ValueError(f"timeseries_pointers.csv row {row}: unmapped Parameter {parameter!r}")

        category = str(row["Category"])
        obj = str(row["Object"])
        if category == "Generator":
            gen_uid = _resolve_generator_object(
                obj, owners.generator_id_by_uid, storage_gen_uid_by_storage_name
            )
            owner_id = owners.generator_id_by_uid[gen_uid]
            unit_type = unit_type_by_uid.get(gen_uid)
            if unit_type is None:
                raise ValueError(
                    f"timeseries_pointers.csv row {row}: generator {gen_uid!r} not in gen.csv"
                )
            owner_type = unit_type_target(unit_type)
            column = gen_uid
        elif category in ("Area", "Region", "Zone"):
            if obj not in owners.area_id_by_name:
                raise ValueError(f"timeseries_pointers.csv row {row}: unmapped Area {obj!r}")
            owner_id = owners.area_id_by_name[obj]
            owner_type = "Area"
            column = obj
        elif category == "Reserve":
            if obj not in owners.reserve_id_by_product:
                raise ValueError(f"timeseries_pointers.csv row {row}: unmapped Reserve {obj!r}")
            owner_id = owners.reserve_id_by_product[obj]
            owner_type = "OnlineReserve"
            # Reserves/ is not uniformly Layout B: Spin_Up_R1/R2/R3 carry a
            # Period column with one object column named after the product
            # (Layout A); Flex_*/Reg_* have no Period column (Layout B, which
            # ignores `column`). `obj` (the reserve product name) is the
            # right column selector either way.
            column = obj
        else:
            raise ValueError(f"timeseries_pointers.csv row {row}: unmapped Category {category!r}")

        csv_path = resolve_case_insensitive_path(source, str(row["Data File"]))
        timestamps, raw_values = read_profile(csv_path, column, resolution_delta)
        values = raw_values * float(row["Scaling Factor"])

        uri, digest = sidecar.write(timestamps, values)

        association = SingleTimeSeries(
            association_id=doc.next_id(),
            owner_id=owner_id,
            owner_type=owner_type,
            owner_category=OwnerCategory.Component,
            time_series_type="SingleTimeSeries",
            name=target.name,
            features={},
            uri=uri,
            data_hash=digest,
            element_type="f64",
            element_shape=[],
            array_shape=[len(values)],
            units="MW",
            quantity_kind=target.quantity_kind,
            unit_system="NATURAL_UNITS",
            time_reference="zoneless",
            initial_timestamp=timestamps[0],
            resolution=resolution_str,
            length=len(values),
        )
        doc.document.time_series_associations.append(TimeSeriesAssociation(association))
