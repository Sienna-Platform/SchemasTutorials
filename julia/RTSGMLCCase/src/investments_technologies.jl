using CSV: CSV
using DataFrames: DataFrame

# Investments existing-device and supply-technology stage (E2/JE2): one `SupplyTechnology`
# candidate plus one `ExistingDevices` supplemental attribute per technology class, built from
# the ReEDS-style generator database
# (`capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv` under
# `investments_source_dir()`). Every one of that file's 155 rows has `IsExistUnit == true` (no
# candidate rows to filter out); `add_supply_technologies!` asserts that rather than assuming it.
#
# Which `tech` classes become candidates (ported from Python's `investments/technologies.py`):
# the two classes with a supply-curve file (`upv`, `wind-ons`), the 5 thermal classes (`gas-cc`,
# `gas-ct`, `o-g-s`, `coalolduns`, `nuclear`), and the 2 hydro classes (`hydED`, `hydEND`) = 9
# total. `distpv` and `csp-ns` are excluded (neither has a supply curve nor counts as
# thermal/hydro); `battery_4` becomes a `StorageTechnology` in a later stage, not a
# `SupplyTechnology`.
#
# `power_systems_type` (R39) is the exact PSY component type name the *operations* campaign would
# build this class's devices as. `region` is the sorted list of zone ids (via the investments
# topology stage's `zone_id_by_bus_number`) where at least one existing device of that class
# sits.

const GENERATOR_DATABASE = joinpath("capacitydata", "ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv")

# The 9 SupplyTechnology candidate classes, mapped to the exact PSY component type name the
# operations campaign builds for that class (R39).
const POWER_SYSTEMS_TYPE_BY_CLASS = Dict{String, String}(
    "gas-cc" => "ThermalStandard",
    "gas-ct" => "ThermalStandard",
    "o-g-s" => "ThermalStandard",
    "coalolduns" => "ThermalStandard",
    "nuclear" => "ThermalStandard",
    "hydED" => "HydroDispatch",
    "hydEND" => "HydroDispatch",
    "upv" => "RenewableDispatch",
    "wind-ons" => "RenewableDispatch",
)

# SupplyTechnology.fuel is only meaningful for thermal classes. Maps each thermal class to the
# source `Fuel` name that indexes `THERMAL_FUEL` (generation.jl) -- reused rather than
# redefining a fuel-name mapping. Non-thermal classes (hydED, hydEND, upv, wind-ons) are absent
# here on purpose and left with fuel = nothing: their source Fuel values (Hydro, Solar, Wind)
# have no THERMAL_FUEL entry and don't need one.
const FUEL_NAME_BY_CLASS = Dict{String, String}(
    "gas-cc" => "NG",
    "gas-ct" => "NG",
    "o-g-s" => "Oil",
    "coalolduns" => "Coal",
    "nuclear" => "Nuclear",
)

"""
    add_supply_technologies!(doc, source::AbstractString, idx::TopologyIndex,
        inv_idx::InvestmentTopologyIndex) -> Dict{String, Int}

Add one `SupplyTechnology` plus one `ExistingDevices` supplemental attribute per class in
[`POWER_SYSTEMS_TYPE_BY_CLASS`](@ref), in sorted class-name order for determinism. Returns a
mapping from class name to the minted `SupplyTechnology` id (later stages need this).
"""
function add_supply_technologies!(
    doc::PortfolioCase,
    source::AbstractString,
    _idx::TopologyIndex,
    inv_idx::InvestmentTopologyIndex,
)
    gen_db = CSV.read(joinpath(source, GENERATOR_DATABASE), DataFrame)
    all(gen_db[!, "IsExistUnit"]) || error(
        "$GENERATOR_DATABASE: expected every row to have IsExistUnit == true " *
        "(this stage does not filter candidate rows)",
    )

    technology_id_by_class = Dict{String, Int}()
    for tech_class in sort(collect(keys(POWER_SYSTEMS_TYPE_BY_CLASS)))
        rows = gen_db[gen_db[!, "tech"] .== tech_class, :]
        isempty(rows) && error("tech class $(repr(tech_class)): no rows in $GENERATOR_DATABASE")

        device_uids = sort(String.(rows[!, "GEN UID"]))
        zone_ids = sort(unique(inv_idx.zone_id_by_bus_number[Int(bus_number)] for bus_number in rows[!, "Bus ID"]))

        if haskey(FUEL_NAME_BY_CLASS, tech_class)
            fuel_name = FUEL_NAME_BY_CLASS[tech_class]
            haskey(THERMAL_FUEL, fuel_name) ||
                error("tech class $(repr(tech_class)): unmapped fuel name $(repr(fuel_name))")
            fuel = [THERMAL_FUEL[fuel_name]]
        else
            fuel = nothing
        end

        technology = PD.SupplyTechnology(;
            id = next_id!(doc),
            name = tech_class,
            power_systems_type = POWER_SYSTEMS_TYPE_BY_CLASS[tech_class],
            region = zone_ids,
            fuel = fuel,
            capital_costs = capital_costs_for(capital_cost_curve(tech_class)),
            financial_data = financial_data_for(tech_class),
        )
        technology_id = add!(doc, technology)
        technology_id_by_class[tech_class] = technology_id

        existing_devices =
            PD.ExistingDevices(; id = next_id!(doc), existing_devices = device_uids)
        PD.add_supplemental_attribute!(doc.document, existing_devices, technology_id)
    end

    return technology_id_by_class
end
