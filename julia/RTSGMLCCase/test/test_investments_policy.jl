# Build the operations stages (topology + generation) then JE1-JE4's investments stages, then
# this task's policy stage on top -- this task needs both JE2's and JE3's outputs, so the fixture
# runs the whole chain rather than just `add_policy_constraints!` in isolation. Mirrors
# `test_investments_storage.jl`'s `_build_storage_technologies` helper.
function _build_policy_constraints(doc)
    op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    idx = RTSGMLCCase.add_topology!(doc, op_src)
    RTSGMLCCase.add_generation!(doc, op_src, idx)

    portfolio = RTSGMLCCase.new_portfolio(
        doc;
        aggregation = "Area",
        base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
    )
    inv_src = RTSGMLCCase.investments_source_dir()
    inv_idx = RTSGMLCCase.add_investment_topology!(portfolio, inv_src, idx)
    supply_ids = RTSGMLCCase.add_supply_technologies!(portfolio, inv_src, idx, inv_idx)
    storage_ids = RTSGMLCCase.add_storage_technologies!(portfolio, inv_src, inv_idx)
    minted = RTSGMLCCase.add_policy_constraints!(portfolio, supply_ids, storage_ids)
    return portfolio, supply_ids, storage_ids, minted
end

# The order `add_policy_constraints!` processes the 6 policy types in -- reused here to build
# each technology's *expected* requirements list in the same order the production code appends
# to it.
const POLICY_TYPES_IN_PROCESSING_ORDER = (
    "CarbonCaps",
    "CarbonTax",
    "CapacityReserveMargin",
    "EnergyShareRequirements",
    "MinimumCapacityRequirements",
    "MaximumCapacityRequirements",
)

# The scenario table from `investments_policy.jl`'s header, expressed as
# policy_type => target_class_set -- the same declarative shape the production code builds from,
# not a re-typed per-class magic-number table.
function _scenario_targets(supply_ids, storage_ids)
    return Dict(
        "CarbonCaps" => Set(RTSGMLCCase.FOSSIL_THERMAL_CLASSES),
        "CarbonTax" => Set(RTSGMLCCase.FOSSIL_THERMAL_CLASSES),
        "CapacityReserveMargin" => union(Set(keys(supply_ids)), Set(keys(storage_ids))),
        "EnergyShareRequirements" => Set(RTSGMLCCase.RENEWABLE_CLASSES),
        "MinimumCapacityRequirements" => Set([RTSGMLCCase.MINIMUM_CAPACITY_CLASS]),
        "MaximumCapacityRequirements" => Set([RTSGMLCCase.MAXIMUM_CAPACITY_CLASS]),
    )
end

# The exact, ordered list of policy ids `class_name` should end up carrying: for each policy type
# in production-processing order, append that type's minted id(s) if `class_name` is one of its
# targets.
function _expected_requirements(class_name, targets_by_policy, minted)
    expected = Int[]
    for policy_type in POLICY_TYPES_IN_PROCESSING_ORDER
        class_name in targets_by_policy[policy_type] && append!(expected, minted[policy_type])
    end
    return expected
end

@testset "exactly 9 policy components: 4 carbon caps plus 1 each of 5 others" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)

    @test length(PowerOpenAPIModels.get_components(portfolio.document, "CarbonCaps")) == 4
    for type_name in (
        "CarbonTax",
        "CapacityReserveMargin",
        "EnergyShareRequirements",
        "MinimumCapacityRequirements",
        "MaximumCapacityRequirements",
    )
        @test length(PowerOpenAPIModels.get_components(portfolio.document, type_name)) == 1
    end
end

@testset "add_policy_constraints! return value matches component counts" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, minted = _build_policy_constraints(doc)

    @test Set(keys(minted)) == Set(POLICY_TYPES_IN_PROCESSING_ORDER)
    @test length(minted["CarbonCaps"]) == 4
    for type_name in POLICY_TYPES_IN_PROCESSING_ORDER
        if type_name != "CarbonCaps"
            @test length(minted[type_name]) == 1
        end
        present_ids =
            Set(c.id for c in PowerOpenAPIModels.get_components(portfolio.document, type_name))
        for component_id in minted[type_name]
            @test component_id in present_ids
        end
    end
end

@testset "carbon caps trajectory values match the scenario table" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)

    caps_by_year = Dict(cap.target_year => cap for cap in PowerOpenAPIModels.get_components(portfolio.document, "CarbonCaps"))
    @test Set(keys(caps_by_year)) == Set(year for (year, _) in RTSGMLCCase.CARBON_CAP_TRAJECTORY)
    for (year, max_mtons) in RTSGMLCCase.CARBON_CAP_TRAJECTORY
        cap = caps_by_year[year]
        @test cap.max_mtons == max_mtons
        @test cap.available == true
    end

    # 80%-by-2050 relative to the 2025 figure.
    cap_2025 = caps_by_year[2025].max_mtons
    cap_2050 = caps_by_year[2050].max_mtons
    @test cap_2050 == cap_2025 * 0.2
end

@testset "carbon tax, capacity reserve margin, and energy share values" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)

    tax = only(PowerOpenAPIModels.get_components(portfolio.document, "CarbonTax"))
    @test tax.target_year == RTSGMLCCase.CARBON_TAX_YEAR
    @test tax.tax_dollars_per_ton == RTSGMLCCase.CARBON_TAX_DOLLARS_PER_TON

    reserve_margin = only(PowerOpenAPIModels.get_components(portfolio.document, "CapacityReserveMargin"))
    @test reserve_margin.target_year == RTSGMLCCase.CAPACITY_RESERVE_MARGIN_YEAR
    @test reserve_margin.capacity_reserve_fraction == RTSGMLCCase.CAPACITY_RESERVE_FRACTION
    @test 0.10 <= reserve_margin.capacity_reserve_fraction <= 0.15

    energy_share = only(PowerOpenAPIModels.get_components(portfolio.document, "EnergyShareRequirements"))
    @test energy_share.target_year == RTSGMLCCase.ENERGY_SHARE_YEAR
    @test energy_share.generation_fraction_requirement == RTSGMLCCase.ENERGY_SHARE_FRACTION
end

@testset "minimum and maximum capacity requirement values" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)

    minimum = only(PowerOpenAPIModels.get_components(portfolio.document, "MinimumCapacityRequirements"))
    @test minimum.target_year == RTSGMLCCase.MINIMUM_CAPACITY_YEAR
    @test minimum.min_capacity_mw == RTSGMLCCase.MINIMUM_CAPACITY_MW

    maximum = only(PowerOpenAPIModels.get_components(portfolio.document, "MaximumCapacityRequirements"))
    @test maximum.target_year == RTSGMLCCase.MAXIMUM_CAPACITY_YEAR
    @test maximum.max_capacity_mw == RTSGMLCCase.MAXIMUM_CAPACITY_MW
end

@testset "every supply and storage technology is bound to exactly the expected policies" begin
    doc = RTSGMLCCase.new_document()
    portfolio, supply_ids, storage_ids, minted = _build_policy_constraints(doc)
    targets_by_policy = _scenario_targets(supply_ids, storage_ids)

    bound_by_entity = Dict{Int, Vector{Int}}()
    for row in portfolio.document.requirements_associations
        push!(get!(bound_by_entity, Int(row.entity_id), Int[]), Int(row.requirement_id))
    end

    for type_name in ("SupplyTechnology", "StorageTechnology")
        for tech in PowerOpenAPIModels.get_components(portfolio.document, type_name)
            expected = _expected_requirements(tech.name, targets_by_policy, minted)
            @test get(bound_by_entity, tech.id, Int[]) == expected
        end
    end
end

@testset "every association resolves to a real component id" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)

    all_ids = Set{Int}()
    for type_name in PowerOpenAPIModels.component_type_names(portfolio.document)
        for component in PowerOpenAPIModels.get_components(portfolio.document, type_name)
            push!(all_ids, component.id)
        end
    end
    for type_name in PowerOpenAPIModels.component_type_names(doc)
        for component in PowerOpenAPIModels.get_components(doc, type_name)
            push!(all_ids, component.id)
        end
    end

    @test !isempty(portfolio.document.requirements_associations)
    for row in portfolio.document.requirements_associations
        @test row.requirement_id in all_ids
        @test row.entity_id in all_ids
    end
end

@testset "no technology component carries a requirements field" begin
    # The membership lives in `requirements_associations`. The generated structs have no
    # `requirements` field at all, which is the point: the earlier draft's list was never in
    # any schema.
    @test !(:requirements in fieldnames(PowerOpenAPIModels.SupplyTechnology))
    @test !(:requirements in fieldnames(PowerOpenAPIModels.StorageTechnology))
end

@testset "validate passes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _, _, _ = _build_policy_constraints(doc)
    PowerOpenAPIModels.validate_document(doc)
    PowerOpenAPIModels.validate_document(portfolio.document)
end
