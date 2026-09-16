function _build_investment_demand(dir)
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    portfolio = RTSGMLCCase.new_portfolio(
        doc;
        aggregation = "Area",
        base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
    )
    inv_src = RTSGMLCCase.investments_source_dir()
    inv_idx = RTSGMLCCase.add_investment_topology!(portfolio, inv_src, idx)
    sidecar = RTSGMLCCase.SidecarWriter(dir)
    demand_ids = RTSGMLCCase.add_demand_requirements!(portfolio, inv_src, sidecar, inv_idx)
    return doc, portfolio, inv_src, sidecar, inv_idx, demand_ids
end

@testset "add_demand_requirements! counts one per zone" begin
    mktempdir() do dir
        doc, portfolio, inv_src, sidecar, inv_idx, demand_ids = _build_investment_demand(dir)

        requirements = PowerOpenAPIModels.get_components(portfolio.document, "DemandRequirement")
        @test length(requirements) == 3
        @test Set(keys(demand_ids)) == Set(["1", "2", "3"])
        @test Set(keys(demand_ids)) == Set(keys(inv_idx.zone_id_by_name))

        PowerOpenAPIModels.validate_document(doc)
    end
end

@testset "DemandRequirement fields match the plan" begin
    mktempdir() do dir
        doc, portfolio, inv_src, sidecar, inv_idx, demand_ids = _build_investment_demand(dir)

        requirements = Dict(r.name => r for r in PowerOpenAPIModels.get_components(portfolio.document, "DemandRequirement"))
        for zone_name in ["1", "2", "3"]
            requirement = requirements[zone_name]
            @test requirement.power_systems_type == "PowerLoad"
            @test requirement.region == [inv_idx.zone_id_by_name[zone_name]]
            @test requirement.value_of_lost_load == 9_000.0
            @test requirement.conformity == "UNDEFINED"  # a String in Julia, an enum in Python
            @test requirement.id == demand_ids[zone_name]
        end
    end
end

@testset "demand time series associations counts and resolution" begin
    mktempdir() do dir
        doc, portfolio, inv_src, sidecar, inv_idx, demand_ids = _build_investment_demand(dir)

        assocs = [
            a.value for a in portfolio.document.time_series_associations if a.value.owner_type == "DemandRequirement"
        ]
        @test length(assocs) == 3
        for sts in assocs
            @test sts.resolution == "PT1H"
            @test sts.length == 8784
            @test sts.array_shape == [8784]
            @test sts.name == "requirement"
            @test sts.quantity_kind == "requirement"
            @test sts.units == "MW"
            @test sts.owner_category == PowerOpenAPIModels.OwnerCategory("Component")
            @test sts.unit_system == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
            @test sts.time_reference == "zoneless"
            @test sts.owner_id in values(demand_ids)
        end
    end
end

@testset "demand series uri resolves and reproduces the source CSV" begin
    mktempdir() do dir
        doc, portfolio, inv_src, sidecar, inv_idx, demand_ids = _build_investment_demand(dir)

        csv_path = joinpath(inv_src, RTSGMLCCase.LOAD_DATA_FILE)
        resolution_str, resolution_delta = RTSGMLCCase.RESOLUTION_BY_SIMULATION["DAY_AHEAD"]

        for (zone_name, requirement_id) in demand_ids
            sts = only(
                a.value for a in portfolio.document.time_series_associations if
                a.value.owner_type == "DemandRequirement" && a.value.owner_id == requirement_id
            )

            path = joinpath(dir, sts.uri)
            @test isfile(path)

            df = DataFrame(Parquet2.Dataset(path); copycols = true)
            @test nrow(df) == 8784

            _, expected_values = RTSGMLCCase.read_profile(csv_path, zone_name, resolution_delta)
            @test df.value == expected_values
            @test sts.data_hash == RTSGMLCCase.data_hash(expected_values)
        end
    end
end
