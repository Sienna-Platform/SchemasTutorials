using Dates: DateTime
using TimeZones: astimezone, @tz_str

# Investments demand-requirement stage: one `DemandRequirement` per zone, plus its hourly
# `requirement` time series, built from `loaddata/RTS_DA_regional_load.csv` (under
# `investments_source_dir()`).
#
# Mapping decisions (mirrors the Python `investments/demand.py`):
#
# - One `DemandRequirement` per zone (3 total, one per RTS Area) -- not per bus. The CSV's three
#   load columns are named `"1"`, `"2"`, `"3"`, matching the zone names JE1's
#   `InvestmentTopologyIndex` already keys on, so no bus-level disaggregation is needed or
#   possible from this file.
# - `power_systems_type = "PowerLoad"`: confirmed by `demand.jl`'s `add_loads!`, which builds the
#   operations campaign's load components as `PD.PowerLoad`.
# - `conformity` is set to the schema's own default (`"UNDEFINED"`), matching the operations
#   `PowerLoad`'s own convention.
# - `value_of_lost_load` is required but has no dataset-sourced figure in scope for this task;
#   see `VALUE_OF_LOST_LOAD` below.
# - Everything else (`new_demand_mw`, `growth_rate`, `new_construction_year`,
#   `unserved_demand_curve`, `requirements`) is left at its schema default.
# - The time series reuses `timeseries.jl`'s already-public `RESOLUTION_BY_SIMULATION` and
#   `read_profile` directly (Layout A -- a `Period` column resetting daily, the zone name as the
#   column selector). The association is built field-for-field to match the shape
#   `timeseries.jl`'s `attach_time_series!` already builds for other owners.

const LOAD_DATA_FILE = "loaddata/RTS_DA_regional_load.csv"

# Illustrative VOLL (value of lost load), USD/MWh. Not sourced from this dataset -- a
# commonly-cited illustrative figure for a capacity-expansion worked example, not a lookup. It
# happens to land near scalars.csv's `cost_dropped_load` row (10000, 2004$/MWh) -- that is
# coincidental plausibility, not a citation: that field is explicitly restricted to historical
# years, and this figure is not derived from it.
const VALUE_OF_LOST_LOAD = 9_000.0

"""
    add_demand_requirements!(doc, source::AbstractString, sidecar::SidecarWriter, inv_idx::InvestmentTopologyIndex) ->
        Dict{String,Int}

Add one `DemandRequirement` per zone (sorted zone-name order) plus its hourly `requirement` time
series, read from `source/loaddata/RTS_DA_regional_load.csv`. Returns the minted
`DemandRequirement` id by zone name.
"""
function add_demand_requirements!(
    doc::PortfolioCase,
    source::AbstractString,
    sidecar::SidecarWriter,
    inv_idx::InvestmentTopologyIndex,
)
    csv_path = joinpath(source, LOAD_DATA_FILE)
    resolution_str, resolution_delta = RESOLUTION_BY_SIMULATION["DAY_AHEAD"]

    demand_requirement_id_by_zone = Dict{String, Int}()
    for zone_name in sort(collect(keys(inv_idx.zone_id_by_name)); by = x -> parse(Int, x))
        timestamps, values = read_profile(csv_path, zone_name, resolution_delta)

        requirement = PD.DemandRequirement(;
            id = next_id!(doc),
            name = zone_name,
            power_systems_type = "PowerLoad",
            region = [inv_idx.zone_id_by_name[zone_name]],
            value_of_lost_load = VALUE_OF_LOST_LOAD,
            # `conformity` carries an "UNDEFINED" default in the schema, but the Julia
            # generator drops defaults where the Python one honors them -- set it so both
            # languages write the same document. Note the *type* differs too: Python
            # generates the `LoadConformity` enum here, Julia a bare `String`.
            conformity = "UNDEFINED",
        )
        requirement_id = add!(doc, requirement)
        demand_requirement_id_by_zone[zone_name] = requirement_id

        uri, digest = write_series!(sidecar, timestamps, values)

        association = PD.SingleTimeSeries(;
            association_id = next_id!(doc),
            owner_id = requirement_id,
            owner_type = "DemandRequirement",
            owner_category = PD.OwnerCategory("Component"),
            time_series_type = "SingleTimeSeries",
            name = "requirement",
            features = PD.TimeSeriesFeatures(),
            uri = uri,
            data_hash = digest,
            element_type = "f64",
            element_shape = Int[],
            array_shape = [length(values)],
            units = "MW",
            quantity_kind = "requirement",
            unit_system = PD.UnitSystem("NATURAL_UNITS"),
            time_reference = "zoneless",
            # Plain UTC `DateTime` in the schema, not a zoned one -- same conversion as
            # `timeseries.jl`.
            initial_timestamp = DateTime(astimezone(timestamps[1], tz"UTC")),
            resolution = resolution_str,
            length = length(values),
        )
        PD.add_time_series_association!(doc.document, PD.TimeSeriesAssociation(association))
    end

    return demand_requirement_id_by_zone
end
