const _EXCLUDED_TECH_CLASSES = Set(["distpv", "csp-ns", "battery_4"])

# Build the operations stages this test needs (topology + generation, so the operations
# component types -- ThermalStandard/HydroDispatch/RenewableDispatch -- are already present in
# the document), then run the investments topology and supply-technology stages on top.
function _build_supply_technologies(doc)
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
    tech_id_by_class = RTSGMLCCase.add_supply_technologies!(portfolio, inv_src, idx, inv_idx)
    return portfolio, idx, inv_idx, tech_id_by_class
end

function _generator_database()
    src = RTSGMLCCase.investments_source_dir()
    return CSV.read(joinpath(src, RTSGMLCCase.GENERATOR_DATABASE), DataFrame)
end

@testset "every row is an existing unit" begin
    gen_db = _generator_database()
    @test nrow(gen_db) == 155
    @test all(gen_db[!, "IsExistUnit"])
end

@testset "exactly 9 supply technologies named by the 9 classes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    techs = PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology")
    @test length(techs) == 9

    expected_classes = Set([
        "gas-cc", "gas-ct", "o-g-s", "coalolduns", "nuclear", "hydED", "hydEND", "upv", "wind-ons",
    ])
    @test Set(keys(tech_id_by_class)) == Set(keys(RTSGMLCCase.POWER_SYSTEMS_TYPE_BY_CLASS)) == expected_classes
    @test isempty(intersect(Set(keys(tech_id_by_class)), _EXCLUDED_TECH_CLASSES))

    gen_db = _generator_database()
    @test _EXCLUDED_TECH_CLASSES ⊆ Set(gen_db[!, "tech"])

    names = Set(t.name for t in techs)
    @test names == Set(keys(tech_id_by_class))
end

@testset "power_systems_type is an R39 string present in the document" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    r39_types = Set(["ThermalStandard", "RenewableDispatch", "HydroDispatch", "EnergyReservoirStorage"])
    @test Set(values(RTSGMLCCase.POWER_SYSTEMS_TYPE_BY_CLASS)) ⊆ r39_types

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology")
        expected = RTSGMLCCase.POWER_SYSTEMS_TYPE_BY_CLASS[tech.name]
        @test tech.power_systems_type == expected
        # The type actually has at least one component under it in this same document (built
        # from the operations stages above), not a deferred check.
        @test length(PowerOpenAPIModels.get_components(doc, tech.power_systems_type)) > 0
    end
end

@testset "existing devices counts match the generator database" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)
    gen_db = _generator_database()

    existing_devices_by_technology_id = Dict(
        assoc.component_id => portfolio.document.supplemental_attributes[i] for
        (i, assoc) in enumerate(portfolio.document.supplemental_attribute_associations) if
        assoc.attribute_type == "ExistingDevices"
    )
    @test length(existing_devices_by_technology_id) == 9

    for (tech_class, technology_id) in tech_id_by_class
        expected_uids = sort(String.(gen_db[gen_db[!, "tech"].==tech_class, "GEN UID"]))
        attribute = existing_devices_by_technology_id[technology_id]
        @test attribute.existing_devices == expected_uids
        @test length(attribute.existing_devices) == count(==(tech_class), gen_db[!, "tech"])
    end

    # Pinned counts from the brief's table.
    @test count(==("gas-ct"), gen_db[!, "tech"]) == 27
    @test count(==("hydED"), gen_db[!, "tech"]) == 19
    @test count(==("o-g-s"), gen_db[!, "tech"]) == 19
end

@testset "supplemental attribute associations point at SupplyTechnology" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    technology_ids = Set(values(tech_id_by_class))
    associations =
        filter(a -> a.attribute_type == "ExistingDevices", portfolio.document.supplemental_attribute_associations)
    @test length(associations) == 9
    for assoc in associations
        @test assoc.component_type == "SupplyTechnology"
        @test assoc.component_id in technology_ids
    end
end

@testset "region resolves to real zone ids" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    zone_ids = Set(values(inv_idx.zone_id_by_name))
    @test !isempty(zone_ids)

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology")
        @test !isempty(tech.region)
        @test Set(tech.region) ⊆ zone_ids
        @test tech.region == sort(tech.region)
    end

    PowerOpenAPIModels.validate_document(doc)
end

@testset "fuel only set for thermal classes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    thermal_classes = Set(["gas-cc", "gas-ct", "o-g-s", "coalolduns", "nuclear"])
    for tech in PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology")
        if tech.name in thermal_classes
            @test tech.fuel !== nothing
            @test length(tech.fuel) == 1
        else
            @test tech.fuel === nothing
        end
    end
end

@testset "financial data fully populated" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, tech_id_by_class = _build_supply_technologies(doc)

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology")
        financial_data = tech.financial_data
        @test financial_data !== nothing
        @test financial_data.capital_recovery_period !== nothing
        @test financial_data.technology_base_year !== nothing
        @test financial_data.debt_fraction !== nothing
        @test financial_data.debt_rate !== nothing
        @test financial_data.return_on_equity !== nothing
        @test financial_data.tax_rate !== nothing
        @test tech.capital_costs !== nothing
    end
end

@testset "validate passes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_supply_technologies(doc)
    PowerOpenAPIModels.validate_document(doc)
end

@testset "IsExistUnit precondition raises when a row is not an existing unit" begin
    mktempdir() do root
        capdir = joinpath(root, "capacitydata")
        mkpath(capdir)
        gen_db = _generator_database()
        bad = copy(gen_db)
        bad[1, "IsExistUnit"] = false
        CSV.write(joinpath(capdir, "ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv"), bad)

        doc = RTSGMLCCase.new_document()
        op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
        idx = RTSGMLCCase.add_topology!(doc, op_src)
        portfolio = RTSGMLCCase.new_portfolio(
            doc;
            aggregation = "Area",
            base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
        )
        inv_idx = RTSGMLCCase.add_investment_topology!(
            portfolio,
            RTSGMLCCase.investments_source_dir(),
            idx,
        )

        err = nothing
        try
            RTSGMLCCase.add_supply_technologies!(portfolio, root, idx, inv_idx)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        @test occursin("IsExistUnit", message)
    end
end

@testset "empty-class precondition raises naming the offending class" begin
    mktempdir() do root
        capdir = joinpath(root, "capacitydata")
        mkpath(capdir)
        gen_db = _generator_database()
        without_upv = gen_db[gen_db[!, "tech"].!="upv", :]
        CSV.write(joinpath(capdir, "ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv"), without_upv)

        doc = RTSGMLCCase.new_document()
        op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
        idx = RTSGMLCCase.add_topology!(doc, op_src)
        portfolio = RTSGMLCCase.new_portfolio(
            doc;
            aggregation = "Area",
            base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
        )
        inv_idx = RTSGMLCCase.add_investment_topology!(
            portfolio,
            RTSGMLCCase.investments_source_dir(),
            idx,
        )

        err = nothing
        try
            RTSGMLCCase.add_supply_technologies!(portfolio, root, idx, inv_idx)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        @test occursin("upv", message)
    end
end
