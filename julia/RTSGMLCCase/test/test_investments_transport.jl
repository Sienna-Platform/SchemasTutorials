function _build_transport_technologies(doc)
    op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    idx = RTSGMLCCase.add_topology!(doc, op_src)
    portfolio = RTSGMLCCase.new_portfolio(
        doc;
        aggregation = "Area",
        base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
    )
    inv_src = RTSGMLCCase.investments_source_dir()
    inv_idx = RTSGMLCCase.add_investment_topology!(portfolio, inv_src, idx)
    ac_id_by_bus_pair, hvdc_id_by_bus_pair = RTSGMLCCase.add_transport_technologies!(portfolio, inv_src, inv_idx)
    return portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair
end

@testset "AC capacity file has 120 rows and 108 unique bus pairs with 12 exact duplicates" begin
    src = RTSGMLCCase.investments_source_dir()
    capacity = CSV.read(joinpath(src, RTSGMLCCase.AC_CAPACITY_FILE), DataFrame)
    @test nrow(capacity) == 120

    grouped_sizes = combine(groupby(capacity, ["From_Bus", "To_Bus"]), nrow => :n)
    @test nrow(grouped_sizes) == 108

    duplicates = grouped_sizes[grouped_sizes[!, :n] .> 1, :]
    @test nrow(duplicates) == 12

    # Every duplicate pair's rows are exactly identical (same MW_f0/MW_r0).
    for row in eachrow(duplicates)
        rows = capacity[
            (capacity[!, "From_Bus"] .== row["From_Bus"]) .& (capacity[!, "To_Bus"] .== row["To_Bus"]), :,
        ]
        @test length(unique(rows[!, "MW_f0"])) == 1
        @test length(unique(rows[!, "MW_r0"])) == 1
    end

    @test all(capacity[!, "MW_f0"] .== capacity[!, "MW_r0"])
end

@testset "AC cost file has 108 rows matching the capacity file's unique pairs" begin
    src = RTSGMLCCase.investments_source_dir()
    capacity = CSV.read(joinpath(src, RTSGMLCCase.AC_CAPACITY_FILE), DataFrame)
    cost = CSV.read(joinpath(src, RTSGMLCCase.AC_COST_FILE), DataFrame)
    @test nrow(cost) == 108

    cost_group_sizes = combine(groupby(cost, ["r", "rr"]), nrow => :n)
    @test all(cost_group_sizes[!, :n] .== 1)

    capacity_pairs = Set(zip(capacity[!, "From_Bus"], capacity[!, "To_Bus"]))
    cost_pairs = Set(zip(cost[!, "r"], cost[!, "rr"]))
    @test capacity_pairs == cost_pairs
end

@testset "HVDC files have exactly one matching row" begin
    src = RTSGMLCCase.investments_source_dir()
    capacity = CSV.read(joinpath(src, RTSGMLCCase.HVDC_CAPACITY_FILE), DataFrame)
    cost = CSV.read(joinpath(src, RTSGMLCCase.HVDC_COST_FILE), DataFrame)
    @test nrow(capacity) == 1
    @test nrow(cost) == 1
    @test (capacity[1, "r"], capacity[1, "rr"]) == ("b113", "b316")
    @test (cost[1, "r"], cost[1, "rr"]) == ("b113", "b316")
    @test Float64(capacity[1, "MW"]) == 100.0
end

@testset "NodalACTransportTechnology count matches a fresh CSV group-by" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build_transport_technologies(doc)

    src = RTSGMLCCase.investments_source_dir()
    capacity = CSV.read(joinpath(src, RTSGMLCCase.AC_CAPACITY_FILE), DataFrame)
    expected_pair_count = nrow(combine(groupby(capacity, ["From_Bus", "To_Bus"]), nrow => :n))

    @test length(PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")) == expected_pair_count
    @test length(ac_id_by_bus_pair) == expected_pair_count
    # Load-bearing for JE7's cross-language equivalence check.
    @test expected_pair_count == 108
end

@testset "duplicate pair capacity is summed" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)

    # b115/b121 is one of the 12 duplicated pairs, MW_f0=500 on each of its two rows -- the
    # resulting NodalACTransportTechnology's capacity must be the sum, 1000, not a single row's
    # 500.
    technologies = Dict(
        tech.name => tech for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")
    )
    @test technologies["AC_115_121"].capacity_limits.max == 1000.0

    # A non-duplicated pair keeps its single-row value unchanged.
    @test technologies["AC_101_102"].capacity_limits.max == 175.0
end

@testset "every AC and HVDC start/end node resolves to a real Node id" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build_transport_technologies(doc)

    # A "node" is an operations ACBus: the schema has no investments Node.
    node_ids = Set(b.id for b in PowerOpenAPIModels.get_components(doc, "ACBus"))
    @test node_ids == Set(values(inv_idx.node_id_by_bus_number))

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")
        @test tech.start_node in node_ids
        @test tech.end_node in node_ids
    end

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalHVDCTransportTechnology")
        @test tech.start_node in node_ids
        @test tech.end_node in node_ids
    end
end

@testset "exactly one NodalHVDCTransportTechnology with capacity 100" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx, ac_id_by_bus_pair, hvdc_id_by_bus_pair = _build_transport_technologies(doc)

    hvdc_techs = PowerOpenAPIModels.get_components(portfolio.document, "NodalHVDCTransportTechnology")
    @test length(hvdc_techs) == 1
    @test length(hvdc_id_by_bus_pair) == 1
    tech = only(hvdc_techs)
    @test tech.capacity_limits.max == 100.0
    @test tech.line_loss === nothing

    expected_start = inv_idx.node_id_by_bus_number[113]
    expected_end = inv_idx.node_id_by_bus_number[316]
    @test tech.start_node == expected_start
    @test tech.end_node == expected_end
end

@testset "AC capital costs are dataset sourced not illustrative" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)

    src = RTSGMLCCase.investments_source_dir()
    cost = CSV.read(joinpath(src, RTSGMLCCase.AC_COST_FILE), DataFrame)
    cost_by_pair = Dict(
        (String(row["r"]), String(row["rr"])) => Float64(row["USD2004perMW"]) for row in eachrow(cost)
    )

    technologies = PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")
    @test length(technologies) == length(cost_by_pair)
    for tech in technologies
        _, from_bus, to_bus = split(tech.name, "_")
        expected_cost = cost_by_pair[("b$from_bus", "b$to_bus")]
        curve = tech.capital_costs.capital_cost.value
        function_data = curve.function_data.value
        @test function_data.proportional_term == expected_cost
        @test function_data.constant_term == 0.0
    end
end

@testset "HVDC capital cost matches the DC cost file" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)

    src = RTSGMLCCase.investments_source_dir()
    cost = CSV.read(joinpath(src, RTSGMLCCase.HVDC_COST_FILE), DataFrame)
    expected_cost = Float64(cost[1, "USD2004perMW"])

    tech = only(PowerOpenAPIModels.get_components(portfolio.document, "NodalHVDCTransportTechnology"))
    curve = tech.capital_costs.capital_cost.value
    function_data = curve.function_data.value
    @test function_data.proportional_term == expected_cost
end

@testset "every transport financial_data has capital_recovery_period 40" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")
        @test tech.financial_data.capital_recovery_period == 40
    end
    for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalHVDCTransportTechnology")
        @test tech.financial_data.capital_recovery_period == 40
    end
end

@testset "resistance/reactance/voltage/unit_size left at schema defaults" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)

    for tech in PowerOpenAPIModels.get_components(portfolio.document, "NodalACTransportTechnology")
        @test tech.resistance == 0.0
        @test tech.reactance == 0.0
        @test tech.voltage == 0.0
        @test tech.unit_size == 0.0
    end
end

@testset "validate passes" begin
    doc = RTSGMLCCase.new_document()
    portfolio, _ = _build_transport_technologies(doc)
    PowerOpenAPIModels.validate_document(doc)
end
