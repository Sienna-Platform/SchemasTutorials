using CSV: CSV
using DataFrames: DataFrame, nrow

# Investments storage-technology stage (E3/JE3): one `StorageTechnology` candidate built from the
# same ReEDS-style generator database E2/JE2 reads (`GENERATOR_DATABASE`, defined in
# `investments_technologies.jl`). Exactly one row has `tech == "battery_4"` (`GEN UID`
# `"313_STORAGE_1"`, `Bus ID` 313, `cap` 50.0 MW, `Storage Roundtrip Efficiency` 85) --
# `add_storage_technologies!` asserts that count rather than assuming it.
#
# `power_systems_type` is `"EnergyReservoirStorage"` (R39's 4th string -- not produced by any of
# E2/JE2's 9 `SupplyTechnology` classes, so this is where it first appears in the document).
#
# `efficiency` reuses the exact split-roundtrip-efficiency formula `generation.jl`'s
# `_build_energy_reservoir_storage` already uses for the operations-side `EnergyReservoirStorage`:
# `sqrt(roundtrip / 100.0)` applied identically to both legs, read from the CSV row (not
# hardcoded). `storage_tech` reuses that same function's `"OTHER_CHEM"` choice for battery
# storage (same field meaning, different field name: `storage_technology_type` there,
# `storage_tech` here). `prime_mover_type` is likewise set to `"BA"`, matching the operations-side
# choice for this same battery unit.
#
# Capacity: `cap` (50.0 MW) is a power figure, so it becomes `capacity_limits_charge`/
# `capacity_limits_discharge` (`MinMax(min=0.0, max=cap)`), not `capacity_limits_energy` -- no
# energy (MWh) capacity figure exists in this dataset, so `capacity_limits_energy` is left
# `nothing` rather than fabricated.
#
# `duration_limits` is left `nothing`: both `storagedata/storage_duration_pshdata.csv` and
# `storagedata/storinmaxfrac.csv` are header-only (zero data rows) in this dataset snapshot -- a
# test in `test_investments_storage.jl` reads both fresh and asserts this.
#
# Capital costs, operation cost, and financial data are external/illustrative (R37) -- see
# `investments_costs.jl` for the figures and their provenance framing.

const BATTERY_TECH_CLASS = "battery_4"

"""
    add_storage_technologies!(doc, source::AbstractString,
        inv_idx::InvestmentTopologyIndex) -> Dict{String, Int}

Add one `StorageTechnology` (class `"battery_4"`) plus one `ExistingDevices` supplemental
attribute to `doc`. Returns a mapping from class name to the minted `StorageTechnology` id --
shaped like [`add_supply_technologies!`](@ref)'s return even though there's only one class today.
"""
function add_storage_technologies!(
    doc::PortfolioCase,
    source::AbstractString,
    inv_idx::InvestmentTopologyIndex,
)
    gen_db = CSV.read(joinpath(source, GENERATOR_DATABASE), DataFrame)
    rows = gen_db[gen_db[!, "tech"] .== BATTERY_TECH_CLASS, :]
    nrow(rows) == 1 || error(
        "expected exactly 1 $(repr(BATTERY_TECH_CLASS)) row in $GENERATOR_DATABASE, " *
        "found $(nrow(rows))",
    )

    device_uids = sort(String.(rows[!, "GEN UID"]))
    zone_ids = sort(unique(inv_idx.zone_id_by_bus_number[Int(bus_number)] for bus_number in rows[!, "Bus ID"]))

    row = rows[1, :]
    cap_mw = Float64(row["cap"])
    leg_efficiency = sqrt(Float64(row["Storage Roundtrip Efficiency"]) / 100.0)

    capital_costs = battery_capital_costs()

    technology = PD.StorageTechnology(;
        id = next_id!(doc),
        name = BATTERY_TECH_CLASS,
        available = true,
        power_systems_type = "EnergyReservoirStorage",
        region = zone_ids,
        prime_mover_type = PD.PrimeMovers("BA"),
        storage_tech = PD.StorageTech("OTHER_CHEM"),
        efficiency = PD.InOut(; in = leg_efficiency, out = leg_efficiency),
        # Julia wraps a `oneOf` in a generated single-field struct where Python uses the bare
        # union, so the MinMax has to be lifted into the wrapper here. Same JSON either way.
        capacity_limits_charge = PD.StorageTechnologyCapacityLimitsCharge(
            PD.MinMax(; min = 0.0, max = cap_mw),
        ),
        capacity_limits_discharge = PD.StorageTechnologyCapacityLimitsDischarge(
            PD.MinMax(; min = 0.0, max = cap_mw),
        ),
        capacity_limits_energy = nothing,
        duration_limits = nothing,
        capital_costs = capital_costs,
        operation_costs = battery_operation_cost(),
        financial_data = financial_data_for(BATTERY_TECH_CLASS),
    )
    technology_id = add!(doc, technology)

    existing_devices =
        PD.ExistingDevices(; id = next_id!(doc), existing_devices = device_uids)
    PD.add_supplemental_attribute!(doc.document, existing_devices, technology_id)

    return Dict{String, Int}(BATTERY_TECH_CLASS => technology_id)
end
