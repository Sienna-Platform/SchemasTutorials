using CSV: CSV
using DataFrames: DataFrame

# Same convention as topology.jl: every component here is natural units on a shared 100 MVA
# base. There is no document-level unit system to inherit it from.
const DEMAND_BASE_POWER = 100.0
const SECONDS_PER_MINUTE = 60.0

# `OnlineReserve.sustained_time` is fixed at one hour, expressed in minutes -- not
# `Timeframe (sec)`-derived, and not the plan's `3600.0` (that number is seconds, this field is
# minutes).
const SUSTAINED_TIME = 60.0

const DIRECTION_BY_SOURCE = Dict{String, PD.ReserveDirection}(
    "Up" => PD.ReserveDirection("UP"),
    "Down" => PD.ReserveDirection("DOWN"),
)

# reserves.csv's `Eligible Regions`/`Eligible Device SubCategories` fields come in two shapes --
# a bare value ("1") or a parenthesized comma list ("(1,2,3)").
function _parse_tuple_field(raw::AbstractString)
    text = strip(raw)
    if startswith(text, "(") && endswith(text, ")")
        text = text[(begin + 1):(end - 1)]
    end
    return [strip(item) for item in split(text, ",") if !isempty(strip(item))]
end

"""
    add_loads!(doc, source::AbstractString, idx::TopologyIndex)

Add one `PowerLoad` per `source/bus.csv` row with nonzero `MW Load` (51 of 73 buses).
`active_power`/`max_active_power` both take `MW Load`, `reactive_power`/`max_reactive_power`
both take `MVAR Load`; every load carries `conformity = "UNDEFINED"`.
"""
function add_loads!(doc::PD.SystemDocument, source::AbstractString, idx::TopologyIndex)
    bus = CSV.read(joinpath(source, "bus.csv"), DataFrame)

    for row in eachrow(bus)
        mw_load = Float64(row["MW Load"])
        iszero(mw_load) && continue

        bus_number = Int(row["Bus ID"])
        haskey(idx.bus_id_by_number, bus_number) ||
            error("bus.csv row $bus_number: unmapped bus in topology index")

        mvar_load = Float64(row["MVAR Load"])
        load = PD.PowerLoad(;
            id = PD.next_id!(doc),
            name = String(row["Bus Name"]),
            available = true,
            bus = idx.bus_id_by_number[bus_number],
            active_power = mw_load,
            max_active_power = mw_load,
            reactive_power = mvar_load,
            max_reactive_power = mvar_load,
            base_power = DEMAND_BASE_POWER,
            power_units = PD.UnitSystem("NATURAL_UNITS"),
            conformity = PD.LoadConformity("UNDEFINED"),
        )
        add!(doc, load)
    end

    return nothing
end

# Eligible generators for one reserve product: `gen.csv` rows whose `Category` is in
# `categories` and whose bus `Area` (joined via `bus.csv`) is in `regions`.
function _eligible_generator_uids(
    gen::DataFrame,
    area_by_bus_number::Dict{Int, Int},
    regions::Set{Int},
    categories::AbstractSet{<:AbstractString},
)
    eligible = String[]
    for row in eachrow(gen)
        String(row["Category"]) in categories || continue
        bus_number = Int(row["Bus ID"])
        haskey(area_by_bus_number, bus_number) ||
            error("gen.csv row $(repr(row["GEN UID"])): unmapped bus $bus_number in bus.csv")
        area_by_bus_number[bus_number] in regions || continue
        push!(eligible, String(row["GEN UID"]))
    end
    return eligible
end

"""
    add_reserves!(doc, source::AbstractString, idx::TopologyIndex, gen_ids::Dict{String,Int}) ->
        Dict{String,Int}

Add one `OnlineReserve` per `source/reserves.csv` row (`time_frame` in minutes =
`Timeframe (sec) / 60`, `sustained_time = 60.0` fixed), then one `PD.add_service_association!`
row per (reserve, eligible generator) pair. Returns the reserve id by product name.

Raises, naming the offending row, on an unmapped `Direction` or an eligible generator absent
from `gen_ids`.
"""
function add_reserves!(
    doc::PD.SystemDocument,
    source::AbstractString,
    idx::TopologyIndex,
    gen_ids::Dict{String, Int},
)
    reserves = CSV.read(joinpath(source, "reserves.csv"), DataFrame)
    gen = CSV.read(joinpath(source, "gen.csv"), DataFrame)
    bus = CSV.read(joinpath(source, "bus.csv"), DataFrame)
    area_by_bus_number = Dict{Int, Int}(
        Int(row["Bus ID"]) => Int(row["Area"]) for row in eachrow(bus)
    )

    reserve_id_by_product = Dict{String, Int}()
    for row in eachrow(reserves)
        product = String(row["Reserve Product"])
        direction_name = String(row["Direction"])
        haskey(DIRECTION_BY_SOURCE, direction_name) || error(
            "reserves.csv row $(repr(product)): unmapped Direction $(repr(direction_name))",
        )
        direction = DIRECTION_BY_SOURCE[direction_name]

        reserve = PD.OnlineReserve(;
            id = PD.next_id!(doc),
            name = product,
            available = true,
            time_frame = Float64(row["Timeframe (sec)"]) / SECONDS_PER_MINUTE,
            requirement = Float64(row["Requirement (MW)"]),
            sustained_time = SUSTAINED_TIME,
            max_output_fraction = 1.0,
            max_participation_factor = 1.0,
            deployed_fraction = 0.0,
            reserve_direction = direction,
        )
        reserve_id = add!(doc, reserve)
        reserve_id_by_product[product] = reserve_id

        regions = Set(parse(Int, v) for v in _parse_tuple_field(String(row["Eligible Regions"])))
        categories = Set(_parse_tuple_field(String(row["Eligible Device SubCategories"])))
        for uid in _eligible_generator_uids(gen, area_by_bus_number, regions, categories)
            haskey(gen_ids, uid) || error(
                "reserves.csv row $(repr(product)): eligible generator $(repr(uid)) not in gen_ids",
            )
            PD.add_service_association!(
                doc,
                PD.ServiceAssociation(; service_id = reserve_id, entity_id = gen_ids[uid]),
            )
        end
    end

    return reserve_id_by_product
end
