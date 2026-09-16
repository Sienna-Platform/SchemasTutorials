# Build the operations stages this test needs (topology + generation, so the operations
# component types -- ThermalStandard/HydroDispatch/RenewableDispatch/EnergyReservoirStorage --
# are already present in the document), then run the investments topology, supply-technology,
# and storage-technology stages on top -- mirrors test_investments_technologies.jl's
# `_build_supply_technologies` helper.
function _build_storage_technologies(doc)
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
    RTSGMLCCase.add_supply_technologies!(portfolio, inv_src, idx, inv_idx)
    storage_id_by_class = RTSGMLCCase.add_storage_technologies!(portfolio, inv_src, inv_idx)
    return portfolio, idx, inv_idx, storage_id_by_class
end

function _battery_row()
    src = RTSGMLCCase.investments_source_dir()
    gen_db = CSV.read(joinpath(src, RTSGMLCCase.GENERATOR_DATABASE), DataFrame)
    rows = gen_db[gen_db[!, "tech"] .== RTSGMLCCase.BATTERY_TECH_CLASS, :]
    @test nrow(rows) == 1
    return rows[1, :]
end

@testset "exactly one battery_4 row in the generator database" begin
    row = _battery_row()
    @test row["GEN UID"] == "313_STORAGE_1"
    @test Int(row["Bus ID"]) == 313
    @test Float64(row["cap"]) == 50.0
    @test Float64(row["Storage Roundtrip Efficiency"]) == 85.0
end

@testset "both duration CSVs have zero data rows" begin
    # R37: duration_limits is left `nothing` on the StorageTechnology because neither duration
    # source has any real data -- this pins that fact against a fresh read so a future dataset
    # refresh that adds rows is caught, not silently left with a stale `nothing`.
    source = RTSGMLCCase.investments_source_dir()
    pshdata = CSV.read(joinpath(source, "storagedata", "storage_duration_pshdata.csv"), DataFrame)
    storinmaxfrac = CSV.read(joinpath(source, "storagedata", "storinmaxfrac.csv"), DataFrame)
    @test nrow(pshdata) == 0
    @test nrow(storinmaxfrac) == 0
end

@testset "exactly one StorageTechnology named battery_4" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, storage_id_by_class = _build_storage_technologies(doc)

    techs = PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology")
    @test length(techs) == 1
    @test Set(keys(storage_id_by_class)) == Set([RTSGMLCCase.BATTERY_TECH_CLASS])

    tech = only(techs)
    @test tech.name == RTSGMLCCase.BATTERY_TECH_CLASS
    @test tech.id == storage_id_by_class[RTSGMLCCase.BATTERY_TECH_CLASS]
end

@testset "power_systems_type is EnergyReservoirStorage and present in the document" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    @test tech.power_systems_type == "EnergyReservoirStorage"
    # R39's 4th string, not produced by any of E2/JE2's 9 SupplyTechnology classes -- confirmed
    # present with at least one real component here.
    @test length(PowerOpenAPIModels.get_components(doc, tech.power_systems_type)) > 0

    supply_types = Set(s.power_systems_type for s in PowerOpenAPIModels.get_components(portfolio.document, "SupplyTechnology"))
    @test "EnergyReservoirStorage" ∉ supply_types
end

@testset "region is the zone containing bus 313" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, storage_id_by_class = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    expected_zone_id = inv_idx.zone_id_by_bus_number[313]
    @test tech.region == [expected_zone_id]
end

@testset "efficiency reuses the generation module formula" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    row = _battery_row()
    expected_leg = sqrt(Float64(row["Storage Roundtrip Efficiency"]) / 100.0)
    @test tech.efficiency.in == expected_leg
    @test tech.efficiency.out == expected_leg
end

@testset "storage_tech and prime_mover_type" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    @test tech.storage_tech == PowerOpenAPIModels.StorageTech("OTHER_CHEM")
    @test tech.prime_mover_type == PowerOpenAPIModels.PrimeMovers("BA")
end

@testset "capacity limits use cap MW for power not energy" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    row = _battery_row()
    cap_mw = Float64(row["cap"])
    # Julia wraps the `oneOf` in a generated single-field struct; `.value` unwraps it.
    @test tech.capacity_limits_charge.value.min == 0.0
    @test tech.capacity_limits_charge.value.max == cap_mw
    @test tech.capacity_limits_discharge.value.min == 0.0
    @test tech.capacity_limits_discharge.value.max == cap_mw
    # cap is a power (MW) figure -- no dataset-backed energy (MWh) capacity figure exists, so
    # capacity_limits_energy is left `nothing`, not fabricated.
    @test tech.capacity_limits_energy === nothing
end

@testset "duration_limits is nothing" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))
    @test tech.duration_limits === nothing
end

@testset "existing devices attribute" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, storage_id_by_class = _build_storage_technologies(doc)

    technology_id = storage_id_by_class[RTSGMLCCase.BATTERY_TECH_CLASS]
    existing_devices_by_component_id = Dict(
        assoc.component_id => portfolio.document.supplemental_attributes[i] for
        (i, assoc) in enumerate(portfolio.document.supplemental_attribute_associations) if
        assoc.attribute_type == "ExistingDevices" && assoc.component_type == "StorageTechnology"
    )
    @test length(existing_devices_by_component_id) == 1
    @test existing_devices_by_component_id[technology_id].existing_devices == ["313_STORAGE_1"]
end

@testset "capital costs, operation cost, and financial data populated" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "StorageTechnology"))

    # The three legs travel in one StorageCapitalCost, not as sibling fields.
    @test tech.capital_costs.charge_capital_cost !== nothing
    @test tech.capital_costs.discharge_capital_cost !== nothing
    @test tech.capital_costs.energy_capital_cost !== nothing
    @test tech.operation_costs !== nothing
    @test tech.financial_data !== nothing
    financial_data = tech.financial_data
    @test financial_data.capital_recovery_period !== nothing
    @test financial_data.technology_base_year !== nothing
    @test financial_data.debt_fraction !== nothing
    @test financial_data.debt_rate !== nothing
    @test financial_data.return_on_equity !== nothing
    @test financial_data.tax_rate !== nothing
end

@testset "validate passes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_storage_technologies(doc)
    PowerOpenAPIModels.validate_document(doc)
end

@testset "expected exactly 1 row precondition raises when battery_4 count differs" begin
    mktempdir() do root
        capdir = joinpath(root, "capacitydata")
        mkpath(capdir)
        src = RTSGMLCCase.investments_source_dir()
        gen_db = CSV.read(joinpath(src, RTSGMLCCase.GENERATOR_DATABASE), DataFrame)
        without_battery = gen_db[gen_db[!, "tech"] .!= RTSGMLCCase.BATTERY_TECH_CLASS, :]
        CSV.write(joinpath(capdir, "ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv"), without_battery)

        doc = RTSGMLCCase.new_document()
        op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
        idx = RTSGMLCCase.add_topology!(doc, op_src)
        portfolio = RTSGMLCCase.new_portfolio(
            doc;
            aggregation = "Area",
            base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
        )
        inv_idx = RTSGMLCCase.add_investment_topology!(portfolio, root, idx)

        err = nothing
        try
            RTSGMLCCase.add_storage_technologies!(portfolio, root, inv_idx)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        @test occursin("battery_4", message)
    end
end
