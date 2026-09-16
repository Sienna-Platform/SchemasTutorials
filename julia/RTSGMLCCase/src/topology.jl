using CSV: CSV
using DataFrames: DataFrame, groupby, combine

# Same convention as the Python tutorial: every component here is expressed in natural units
# on a shared 100 MVA base (R12a). There is no document-level unit system to inherit it from.
const TOPOLOGY_BASE_POWER = 100.0

"""
    TopologyIndex

Cross-reference from `bus.csv` keys to the ids `add_topology!` minted, consumed by later stages
(branches, generators, ...) that need to point at a bus/area/zone by its source-data key rather
than its component id.
"""
struct TopologyIndex
    bus_id_by_number::Dict{Int, Int}
    area_id_by_name::Dict{String, Int}
    zone_id_by_name::Dict{String, Int}
end

# RTS spells the reference bus type "Ref"; the schema's `ACBusType` enum spells it "REF". Every
# other RTS spelling ("PQ", "PV") already matches the enum uppercased. `ACBusType` is a real enum
# type in both languages now, and its constructor rejects anything outside the listed values — so
# a typo like "ref " fails here, at the row that carries it, instead of riding into the document.
function _normalize_bustype(raw::AbstractString)
    if raw == "Ref"
        return PD.ACBusType("REF")
    end
    return PD.ACBusType(uppercase(raw))
end

# `MW Load`/`MVAR Load` summed over the buses that share one `Area` (or `Zone`) value. R24: the
# schema does not derive this for us — `peak_active_power`/`peak_reactive_power` are plain
# required fields, and the only source of truth for them is this bus-level load.
function _load_sums(bus::DataFrame, groupcol::AbstractString)
    sums = combine(groupby(bus, groupcol), "MW Load" => sum => :mw, "MVAR Load" => sum => :mvar)
    return Dict(row[groupcol] => (row.mw, row.mvar) for row in eachrow(sums))
end

"""
    add_topology!(doc, source::AbstractString) -> TopologyIndex

Add `Area`, `LoadZone`, `ACBus`, and `FixedAdmittance` components read from `source/bus.csv` to
`doc`. Returns a `TopologyIndex` mapping source keys to minted ids for later stages to consume.
"""
function add_topology!(doc::PD.SystemDocument, source::AbstractString)
    bus = CSV.read(joinpath(source, "bus.csv"), DataFrame)

    area_sums = _load_sums(bus, "Area")
    zone_sums = _load_sums(bus, "Zone")

    # One `Area` per distinct `Area` value, one `LoadZone` per distinct `Zone` value — 21 zones
    # nested under 3 areas, not one zone per area. RTS's own `Zone` column is finer-grained than
    # `Area`; collapsing to 3 load zones (as the PTDP reference does) would discard that detail.
    # Sorted numeric order is load-bearing, not cosmetic: a later cross-language test asserts
    # Julia and Python mint identical id sequences, and Python sorts the raw numeric values
    # before stringifying — match that exactly or the ids diverge.
    area_id_by_name = Dict{String, Int}()
    for area_value in sort(unique(bus[!, "Area"]))
        name = string(Int(area_value))
        mw, mvar = area_sums[area_value]
        area = PD.Area(;
            id = PD.next_id!(doc),
            name = name,
            peak_active_power = mw,
            peak_reactive_power = mvar,
            load_response = 0.0,
            base_power = TOPOLOGY_BASE_POWER,
            power_units = PD.UnitSystem("NATURAL_UNITS"),
        )
        area_id_by_name[name] = add!(doc, area)
    end

    zone_id_by_name = Dict{String, Int}()
    for zone_value in sort(unique(bus[!, "Zone"]))
        name = string(Int(zone_value))
        mw, mvar = zone_sums[zone_value]
        zone = PD.LoadZone(;
            id = PD.next_id!(doc),
            name = name,
            peak_active_power = mw,
            peak_reactive_power = mvar,
            base_power = TOPOLOGY_BASE_POWER,
            power_units = PD.UnitSystem("NATURAL_UNITS"),
        )
        zone_id_by_name[name] = add!(doc, zone)
    end

    bus_id_by_number = Dict{Int, Int}()
    for row in eachrow(bus)
        bus_number = Int(row["Bus ID"])
        area_name = string(Int(row["Area"]))
        zone_name = string(Int(row["Zone"]))
        haskey(area_id_by_name, area_name) || error("bus $bus_number: unmapped area $(repr(area_name))")
        haskey(zone_id_by_name, zone_name) || error("bus $bus_number: unmapped zone $(repr(zone_name))")

        acbus = PD.ACBus(;
            id = PD.next_id!(doc),
            number = bus_number,
            name = String(row["Bus Name"]),
            available = true,
            bustype = _normalize_bustype(String(row["Bus Type"])),
            # `V Angle` is degrees in the source; the schema's `angle` field is radians.
            angle = deg2rad(Float64(row["V Angle"])),
            magnitude = Float64(row["V Mag"]),
            voltage_limits = PD.MinMax(; min = 0.95, max = 1.05),
            base_voltage = Float64(row["BaseKV"]),
            area = area_id_by_name[area_name],
            load_zone = zone_id_by_name[zone_name],
        )
        bus_id = add!(doc, acbus)
        bus_id_by_number[bus_number] = bus_id

        # R3: three buses (106 Alber, 206 Bajer, 306 Camus) carry a nonzero `MVAR Shunt B`.
        # The task brief's premise ("RTS has no shunts, so raise on any nonzero value") is
        # false — emit a `FixedAdmittance` instead of silently dropping the reactive
        # compensation these buses actually have.
        mw_shunt_g = Float64(row["MW Shunt G"])
        mvar_shunt_b = Float64(row["MVAR Shunt B"])
        if !iszero(mw_shunt_g) || !iszero(mvar_shunt_b)
            shunt = PD.FixedAdmittance(;
                id = PD.next_id!(doc),
                name = "$(row["Bus Name"])_shunt",
                available = true,
                bus = bus_id,
                y = PD.ComplexNumber(; real = mw_shunt_g, imag = mvar_shunt_b),
                base_power = TOPOLOGY_BASE_POWER,
                # `admittance_units` defaults to the bare string "COMPONENT_MVAR" rather than a
                # NATURAL_UNITS-equivalent value — set it explicitly or the shunt silently
                # contradicts every other natural-units component in the document.
                admittance_units = PD.ShuntAdmittanceUnitBasis("NATURAL_UNITS"),
            )
            add!(doc, shunt)
        end
    end

    return TopologyIndex(bus_id_by_number, area_id_by_name, zone_id_by_name)
end
