# Investments policy-constraints stage (E5/JE5): six illustrative policy component types --
# `CarbonCaps`, `CarbonTax`, `CapacityReserveMargin`, `EnergyShareRequirements`,
# `MinimumCapacityRequirements`, `MaximumCapacityRequirements` -- wired to the
# `SupplyTechnology`/`StorageTechnology` candidates they constrain.
#
# None of the values below come from `RTS_inputs` or any other dataset file. This is a worked
# policy scenario invented for this tutorial (an 80%-by-2050 carbon cap trajectory, a reserve
# margin inside the usual 10-15% band, an illustrative RPS-style energy share, and one min/max
# capacity requirement each) -- a reader building a real case replaces every number here.
#
# None of the six policy types carries a `region`/`technology` field of its own, and neither does
# a technology carry a list of the policies that bind it. The link is an *association table*:
# `PortfolioDocument.requirements_associations`, one `RequirementAssociation` row per
# (requirement, member) pair, exactly as `service_associations` links a reserve product to its
# contributing generators. `add_policy_constraints!` mints each policy component first, then
# records one row per technology it targets.
#
# Earlier drafts instead pushed the policy id onto a `requirements` list on the technology
# itself. No release of SiennaSchemas has ever defined that field.

# The 4 fossil-thermal SupplyTechnology candidate classes (JE2's 9 minus nuclear/hydED/hydEND/
# upv/wind-ons, which don't burn carbon fuel).
const FOSSIL_THERMAL_CLASSES = ("gas-cc", "gas-ct", "o-g-s", "coalolduns")

# The 2 renewable SupplyTechnology candidate classes.
const RENEWABLE_CLASSES = ("upv", "wind-ons")

# (target_year, max_mtons) checkpoints of the 80%-by-2050 carbon cap trajectory. 1.6 is exactly
# 80% below 8.0.
const CARBON_CAP_TRAJECTORY = ((2025, 8.0), (2030, 6.5), (2040, 3.5), (2050, 1.6))

const CARBON_TAX_YEAR = 2030
const CARBON_TAX_DOLLARS_PER_TON = 15.0

const CAPACITY_RESERVE_MARGIN_YEAR = 2030
const CAPACITY_RESERVE_FRACTION = 0.13

const ENERGY_SHARE_YEAR = 2030
const ENERGY_SHARE_FRACTION = 0.30

const MINIMUM_CAPACITY_YEAR = 2035
const MINIMUM_CAPACITY_MW = 200.0
const MINIMUM_CAPACITY_CLASS = "wind-ons"

const MAXIMUM_CAPACITY_YEAR = 2035
const MAXIMUM_CAPACITY_MW = 0.0
const MAXIMUM_CAPACITY_CLASS = "coalolduns"

"""
    add_policy_constraints!(doc::PortfolioCase, supply_ids::Dict{String, Int},
        storage_ids::Dict{String, Int}) -> Dict{String, Vector{Int}}

Add the 9 illustrative policy components described in this module's header, then wire each
one's `requirements` targets. `supply_ids` and `storage_ids` are `add_supply_technologies!`'s and
`add_storage_technologies!`'s return values (class name -> minted id). Returns a mapping from
policy-type name to the list of minted ids for that type.
"""
function add_policy_constraints!(
    doc::PortfolioCase,
    supply_ids::Dict{String, Int},
    storage_ids::Dict{String, Int},
)
    minted = Dict{String, Vector{Int}}()

    carbon_cap_ids = Int[]
    for (year, max_mtons) in CARBON_CAP_TRAJECTORY
        component_id = add!(
            doc,
            PD.CarbonCaps(; id = next_id!(doc), name = "Carbon cap $year", available = true, target_year = year, max_mtons = max_mtons),
        )
        push!(carbon_cap_ids, component_id)
        for tech_class in FOSSIL_THERMAL_CLASSES
            add_requirement_association!(doc, component_id, supply_ids[tech_class])
        end
    end
    minted["CarbonCaps"] = carbon_cap_ids

    carbon_tax_id = add!(
        doc,
        PD.CarbonTax(;
            id = next_id!(doc),
            name = "Carbon tax $CARBON_TAX_YEAR",
            available = true,
            target_year = CARBON_TAX_YEAR,
            tax_dollars_per_ton = CARBON_TAX_DOLLARS_PER_TON,
        ),
    )
    for tech_class in FOSSIL_THERMAL_CLASSES
        add_requirement_association!(doc, carbon_tax_id, supply_ids[tech_class])
    end
    minted["CarbonTax"] = [carbon_tax_id]

    reserve_margin_id = add!(
        doc,
        PD.CapacityReserveMargin(;
            id = next_id!(doc),
            name = "Capacity reserve margin $CAPACITY_RESERVE_MARGIN_YEAR",
            available = true,
            target_year = CAPACITY_RESERVE_MARGIN_YEAR,
            capacity_reserve_fraction = CAPACITY_RESERVE_FRACTION,
        ),
    )
    for tech_class in sort(collect(keys(supply_ids)))
        add_requirement_association!(doc, reserve_margin_id, supply_ids[tech_class])
    end
    for tech_class in sort(collect(keys(storage_ids)))
        add_requirement_association!(doc, reserve_margin_id, storage_ids[tech_class])
    end
    minted["CapacityReserveMargin"] = [reserve_margin_id]

    energy_share_id = add!(
        doc,
        PD.EnergyShareRequirements(;
            id = next_id!(doc),
            name = "RPS $ENERGY_SHARE_YEAR",
            available = true,
            target_year = ENERGY_SHARE_YEAR,
            generation_fraction_requirement = ENERGY_SHARE_FRACTION,
        ),
    )
    for tech_class in RENEWABLE_CLASSES
        add_requirement_association!(doc, energy_share_id, supply_ids[tech_class])
    end
    minted["EnergyShareRequirements"] = [energy_share_id]

    minimum_capacity_id = add!(
        doc,
        PD.MinimumCapacityRequirements(;
            id = next_id!(doc),
            name = "Wind capacity floor $MINIMUM_CAPACITY_YEAR",
            available = true,
            target_year = MINIMUM_CAPACITY_YEAR,
            min_capacity_mw = MINIMUM_CAPACITY_MW,
        ),
    )
    add_requirement_association!(doc, minimum_capacity_id, supply_ids[MINIMUM_CAPACITY_CLASS])
    minted["MinimumCapacityRequirements"] = [minimum_capacity_id]

    maximum_capacity_id = add!(
        doc,
        PD.MaximumCapacityRequirements(;
            id = next_id!(doc),
            name = "Coal phase-out $MAXIMUM_CAPACITY_YEAR",
            available = true,
            target_year = MAXIMUM_CAPACITY_YEAR,
            max_capacity_mw = MAXIMUM_CAPACITY_MW,
        ),
    )
    add_requirement_association!(doc, maximum_capacity_id, supply_ids[MAXIMUM_CAPACITY_CLASS])
    minted["MaximumCapacityRequirements"] = [maximum_capacity_id]

    return minted
end
