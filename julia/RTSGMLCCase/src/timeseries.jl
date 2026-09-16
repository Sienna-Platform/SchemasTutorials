using CSV: CSV
using DataFrames: DataFrame, nrow, names
using Dates: Dates, DateTime
using TimeZones: ZonedDateTime, astimezone, @tz_str

# Simulation -> (resolution string, per-step Period). `PT1H`/`PT5M` reverses the older task
# plans' `PT3600S`/`PT300S` -- the actual Python `timeseries.py` (the ground truth here) uses
# `PT1H`/`PT5M`, confirmed by its own docstring ("R32 reverses the plan's PT3600S/PT300S").
const RESOLUTION_BY_SIMULATION = Dict{String, Tuple{String, Dates.Period}}(
    "DAY_AHEAD" => ("PT1H", Dates.Hour(1)),
    "REAL_TIME" => ("PT5M", Dates.Minute(5)),
)

# `Parameter` -> the association's `(name, quantity_kind)`. Ported from Python's
# `PARAMETER_TARGETS` verbatim -- not a single hardcoded `quantity_kind`, a 5-entry map.
const PARAMETER_TARGETS = Dict{String, NamedTuple{(:name, :quantity_kind), Tuple{String, String}}}(
    "PMax MW" => (name = "max_active_power", quantity_kind = "active_power"),
    "PMin MW" => (name = "min_active_power", quantity_kind = "active_power"),
    "MW Load" => (name = "max_active_power", quantity_kind = "active_power"),
    "Requirement" => (name = "requirement", quantity_kind = "active_power"),
    "Natural_Inflow" => (name = "inflow", quantity_kind = "power"),
)

"""
    TimeSeriesOwners

The id maps time-series pointers resolve owners against, bundled from the earlier stages'
return values: `generator_id_by_uid` (from [`add_generation!`](@ref)), `area_id_by_name` (from
`idx.area_id_by_name`, [`add_topology!`](@ref)), `reserve_id_by_product` (from
[`add_reserves!`](@ref)).
"""
struct TimeSeriesOwners
    generator_id_by_uid::Dict{String, Int}
    area_id_by_name::Dict{String, Int}
    reserve_id_by_product::Dict{String, Int}
end

# Many pointer rows share one underlying data file (e.g. every WIND object shares one file),
# and some REAL_TIME files run to 100k+ rows, so re-reading per pointer is wasteful -- mirrors
# Python's `@lru_cache`d `_load_csv`.
const _CSV_CACHE = Dict{String, DataFrame}()

function _load_csv(csv_path::AbstractString)
    return get!(_CSV_CACHE, csv_path) do
        return CSV.read(csv_path, DataFrame)
    end
end

function _daily_origin(df::DataFrame, row_index::Int)
    year = Int(df[row_index, "Year"])
    month = Int(df[row_index, "Month"])
    day = Int(df[row_index, "Day"])
    return ZonedDateTime(DateTime(year, month, day), tz"UTC")
end

function _layout_a_timestamps(df::DataFrame, resolution::Dates.Period)
    n = nrow(df)
    timestamps = Vector{ZonedDateTime}(undef, n)
    for i in 1:n
        period = Int(df[i, "Period"])
        timestamps[i] = _daily_origin(df, i) + resolution * (period - 1)
    end
    return timestamps
end

function _read_layout_a(
    df::DataFrame,
    column::Union{AbstractString, Nothing},
    resolution::Dates.Period,
)
    column === nothing && error("Layout A (a Period column is present) requires a column name")
    String(column) in names(df) ||
        error("column $(repr(column)) not found; available columns: $(names(df))")
    timestamps = _layout_a_timestamps(df, resolution)
    values = Float64.(df[!, String(column)])
    return timestamps, values
end

function _read_layout_b(df::DataFrame, resolution::Dates.Period)
    period_columns = [c for c in names(df) if !(c in ("Year", "Month", "Day"))]
    n_days = nrow(df)
    n_periods = length(period_columns)

    timestamps = Vector{ZonedDateTime}(undef, n_days * n_periods)
    values = Vector{Float64}(undef, n_days * n_periods)
    idx = 0
    for i in 1:n_days
        origin = _daily_origin(df, i)
        for (k, col) in enumerate(period_columns)
            idx += 1
            timestamps[idx] = origin + resolution * (k - 1)
            values[idx] = Float64(df[i, col])
        end
    end
    return timestamps, values
end

"""
    read_profile(csv_path, column, resolution::Dates.Period) -> (timestamps, values)

Read one RTS time-series data file, dispatching on layout: Layout A
(`Year,Month,Day,Period,<object1>,...`, `Period` resets every day) selects `column`; Layout B
(`Year,Month,Day,1,2,...`, one row per day, no object column -- some `Reserves/` files) ignores
`column` and flattens the whole file row-major (day by day, period ascending). Detected by
whether a `Period` column is present. Both paths return `(timestamps::Vector{ZonedDateTime},
values::Vector{Float64})`.
"""
function read_profile(
    csv_path::AbstractString,
    column::Union{AbstractString, Nothing},
    resolution::Dates.Period,
)
    df = _load_csv(String(csv_path))
    if "Period" in names(df)
        return _read_layout_a(df, column, resolution)
    end
    return _read_layout_b(df, resolution)
end

"""
    resolve_case_insensitive_path(base::AbstractString, relative::AbstractString) -> String

Resolve `relative` (e.g. `"../timeseries_data_files/HYDRO/x.csv"`) against `base`'s actual
on-disk entries, one path component at a time, falling back to a case-insensitive match when no
exact-case entry exists.

RTS-GMLC's own `timeseries_pointers.csv` disagrees with the source tree's real casing in two
places: the `HYDRO` directory is really `Hydro` on disk (80 of 282 pointers), and
`Load/REAL_TIME_regional_load.csv` is really `REAL_TIME_regional_Load.csv`. Both resolve
silently on a case-insensitive filesystem (macOS default) and raise on a case-sensitive one
(Linux, most CI) -- this function makes the lookup case-insensitive deliberately, rather than
relying on the filesystem to paper over the mismatch.

Raises (naming the component and `relative`) if a component has zero or more than one
case-insensitive match -- never falls back silently on an ambiguous or missing entry.
"""
function resolve_case_insensitive_path(base::AbstractString, relative::AbstractString)
    current = String(base)
    for part in splitpath(relative)
        if part == ".."
            current = dirname(current)
            continue
        end
        if part == "."
            continue
        end

        entries = try
            readdir(current)
        catch
            error("cannot resolve $(repr(relative)) against $base: $current does not exist")
        end

        if part in entries
            current = joinpath(current, part)
            continue
        end
        matches = [entry for entry in entries if lowercase(entry) == lowercase(part)]
        if length(matches) == 1
            current = joinpath(current, matches[1])
        elseif isempty(matches)
            error(
                "cannot resolve $(repr(relative)) against $base: no entry named " *
                "$(repr(part)) (case-insensitively) in $current",
            )
        else
            error(
                "cannot resolve $(repr(relative)) against $base: ambiguous case-insensitive " *
                "match for $(repr(part)) in $current: $matches",
            )
        end
    end
    return current
end

# The `GEN UID` a Generator-category pointer's `Object` resolves to -- itself if it already is
# one, else its owner via `storage.csv`'s `Storage` -> `GEN UID` column. The resolved `GEN UID`
# also names the profile's data column.
function _resolve_generator_object(
    obj::AbstractString,
    generator_id_by_uid::Dict{String, Int},
    storage_gen_uid_by_storage_name::Dict{String, String},
)
    haskey(generator_id_by_uid, obj) && return String(obj)
    resolved = get(storage_gen_uid_by_storage_name, obj, nothing)
    if resolved !== nothing && haskey(generator_id_by_uid, resolved)
        return resolved
    end
    error(
        "Generator Object $(repr(obj)) resolves through neither GEN UID nor storage.csv's " *
        "Storage -> GEN UID map",
    )
end

_pointer_row_id(row) = "(Simulation=$(repr(row["Simulation"])), Category=$(repr(row["Category"])), " *
                       "Object=$(repr(row["Object"])), Parameter=$(repr(row["Parameter"])))"

"""
    attach_time_series!(doc, source::AbstractString, sidecar::SidecarWriter, owners::TimeSeriesOwners)

Attach one `SingleTimeSeries` association per `source/timeseries_pointers.csv` row, writing
each profile through `sidecar` first. Raises (naming the row) on any unmapped `Simulation`,
`Category`, `Parameter`, or unresolvable owner.
"""
function attach_time_series!(
    doc::PD.SystemDocument,
    source::AbstractString,
    sidecar::SidecarWriter,
    owners::TimeSeriesOwners,
)
    pointers = CSV.read(joinpath(source, "timeseries_pointers.csv"), DataFrame)
    storage = CSV.read(joinpath(source, "storage.csv"), DataFrame)
    storage_gen_uid_by_storage_name = Dict{String, String}(
        String(row["Storage"]) => String(row["GEN UID"]) for row in eachrow(storage)
    )
    gen = CSV.read(joinpath(source, "gen.csv"), DataFrame)
    unit_type_by_uid = Dict{String, String}(
        String(row["GEN UID"]) => String(row["Unit Type"]) for row in eachrow(gen)
    )

    for row in eachrow(pointers)
        row_id = _pointer_row_id(row)

        simulation = String(row["Simulation"])
        haskey(RESOLUTION_BY_SIMULATION, simulation) ||
            error("timeseries_pointers.csv row $row_id: unmapped Simulation $(repr(simulation))")
        resolution_str, resolution_delta = RESOLUTION_BY_SIMULATION[simulation]

        parameter = String(row["Parameter"])
        haskey(PARAMETER_TARGETS, parameter) ||
            error("timeseries_pointers.csv row $row_id: unmapped Parameter $(repr(parameter))")
        target = PARAMETER_TARGETS[parameter]

        category = String(row["Category"])
        obj = String(row["Object"])
        owner_id = 0
        owner_type = ""
        column = ""
        if category == "Generator"
            gen_uid = _resolve_generator_object(
                obj,
                owners.generator_id_by_uid,
                storage_gen_uid_by_storage_name,
            )
            owner_id = owners.generator_id_by_uid[gen_uid]
            haskey(unit_type_by_uid, gen_uid) ||
                error("timeseries_pointers.csv row $row_id: generator $(repr(gen_uid)) not in gen.csv")
            owner_type = unit_type_target(unit_type_by_uid[gen_uid])
            column = gen_uid
        elseif category == "Area" || category == "Region" || category == "Zone"
            haskey(owners.area_id_by_name, obj) ||
                error("timeseries_pointers.csv row $row_id: unmapped Area $(repr(obj))")
            owner_id = owners.area_id_by_name[obj]
            owner_type = "Area"
            column = obj
        elseif category == "Reserve"
            haskey(owners.reserve_id_by_product, obj) ||
                error("timeseries_pointers.csv row $row_id: unmapped Reserve $(repr(obj))")
            owner_id = owners.reserve_id_by_product[obj]
            owner_type = "OnlineReserve"
            # Reserves/ is not uniformly Layout B: Spin_Up_R1/R2/R3 carry a Period column with
            # one object column named after the product (Layout A); Flex_*/Reg_* have no
            # Period column (Layout B, which ignores `column`). `obj` (the reserve product
            # name) is the right column selector either way.
            column = obj
        else
            error("timeseries_pointers.csv row $row_id: unmapped Category $(repr(category))")
        end

        csv_path = resolve_case_insensitive_path(source, String(row["Data File"]))
        timestamps, raw_values = read_profile(csv_path, column, resolution_delta)
        values = raw_values .* Float64(row["Scaling Factor"])

        uri, digest = write_series!(sidecar, timestamps, values)

        association = PD.SingleTimeSeries(;
            association_id = PD.next_id!(doc),
            owner_id = owner_id,
            owner_type = owner_type,
            owner_category = PD.OwnerCategory("Component"),
            time_series_type = "SingleTimeSeries",
            name = target.name,
            features = PD.TimeSeriesFeatures(),
            uri = uri,
            data_hash = digest,
            element_type = "f64",
            element_shape = Int[],
            array_shape = [length(values)],
            units = "MW",
            quantity_kind = target.quantity_kind,
            unit_system = PD.UnitSystem("NATURAL_UNITS"),
            time_reference = "zoneless",
            # `initial_timestamp` is a plain UTC `DateTime` in the schema, not a zoned one:
            # convert to UTC first so a non-UTC source instant lands on the right wall clock
            # rather than being reinterpreted.
            initial_timestamp = DateTime(astimezone(timestamps[1], tz"UTC")),
            resolution = resolution_str,
            length = length(values),
        )
        PD.add_time_series_association!(doc, PD.TimeSeriesAssociation(association))
    end

    return nothing
end
