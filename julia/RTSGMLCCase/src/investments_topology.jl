using CSV: CSV
using DataFrames: DataFrame

# Investments topology stage: the cross-reference later investment stages use to point their
# `region` fields at components that already exist.
#
# This stage adds nothing to the document. It is a chapter about a gap.
#
# SiennaSchemas 0.1.0 defines no `Node` and no `Zone` — the investments group has no topology
# component at all — while PowerSystemsInvestmentsPortfolios.jl still has both structs. The
# schema is the side that is behind, and until it catches up a portfolio cannot mint its own
# topology.
#
# What it can do is reuse the operations topology, already in the base system. Every investments
# technology's `region` is a `Vector{Int}` described as "Location where the component applies.
# Can be a zone or node" — ids with no declared target type. So this stage points them at the
# operations components that carry the same meaning:
#
# - a *node* is the `ACBus` minted by `topology.jl` (73 total),
# - a *zone* is the `Area` minted there too (3 total: "1", "2", "3").
#
# Zones are RTS *Areas*, not `bus.csv`'s `Zone` column (21 values, which is what the operations
# `LoadZone` models) and not `hierarchy_rts.csv`'s `ba` column (5 ReEDS balancing areas).
#
# An earlier draft also emitted a `TopologyMapping` supplemental attribute per zone, listing its
# member bus names. That is dropped: once a zone *is* an `Area`, the membership is already
# recorded by each `ACBus`'s own `area` field, and a `TopologyMapping` would only restate it in a
# second place nothing keeps in sync. It would also have to attach to a component in the *other*
# document, which `add_supplemental_attribute!` rejects outright.
#
# `add_investment_topology!`'s `source` parameter is accepted for signature symmetry with later
# investment stages (E2+) that do read from `investments_source_dir()`, but this stage reads
# nothing under it — every value comes from the operations `bus.csv` and the `TopologyIndex` it
# is handed.

"""
    InvestmentTopologyIndex

Cross-reference from source-data keys to the operations component ids that investments `region`
fields point at, consumed by later stages (E2+).

The ids are operations `ACBus` and `Area` ids, living in the base system — not ids of any
investments component.
"""
struct InvestmentTopologyIndex
    node_id_by_bus_number::Dict{Int, Int}
    zone_id_by_name::Dict{String, Int}
    zone_id_by_bus_number::Dict{Int, Int}
end

"""
    add_investment_topology!(doc, source::AbstractString, idx::TopologyIndex) -> InvestmentTopologyIndex

Return the `InvestmentTopologyIndex` later stages use as `region` targets. Adds nothing to `doc`.

`doc` is still taken, and the bus/area consistency below still checked, because both are what a
reader would expect of this stage, and because the check catches an operations/investments
mismatch here rather than three stages later.
"""
function add_investment_topology!(
    doc::PortfolioCase,
    _source::AbstractString,
    idx::TopologyIndex,
)
    bus = CSV.read(joinpath(rts_source_dir(), SOURCE_DATA, "bus.csv"), DataFrame)

    zone_id_by_bus_number = Dict{Int, Int}()
    for row in eachrow(bus)
        bus_number = Int(row["Bus ID"])
        haskey(idx.bus_id_by_number, bus_number) ||
            error("bus $bus_number: not present in operations TopologyIndex")
        zone_name = string(Int(row["Area"]))
        haskey(idx.area_id_by_name, zone_name) ||
            error("bus $bus_number: unmapped area $(repr(zone_name))")
        zone_id_by_bus_number[bus_number] = idx.area_id_by_name[zone_name]
    end

    return InvestmentTopologyIndex(
        copy(idx.bus_id_by_number),
        copy(idx.area_id_by_name),
        zone_id_by_bus_number,
    )
end
