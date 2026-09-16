function _demand_built_case()
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    gen_ids = RTSGMLCCase.add_generation!(doc, src, idx)
    RTSGMLCCase.add_loads!(doc, src, idx)
    reserve_ids = RTSGMLCCase.add_reserves!(doc, src, idx, gen_ids)
    return doc, src, reserve_ids
end

@testset "loads one per nonzero bus" begin
    doc, src, _ = _demand_built_case()
    bus = CSV.read(joinpath(src, "bus.csv"), DataFrame)
    expected = count(!iszero, Float64.(bus[!, "MW Load"]))

    @test expected == 51
    @test length(PowerOpenAPIModels.get_components(doc, "PowerLoad")) == expected

    PowerOpenAPIModels.validate_document(doc)
end

@testset "load fields match reference row 101" begin
    doc, src, _ = _demand_built_case()
    bus = CSV.read(joinpath(src, "bus.csv"), DataFrame)
    row = only(filter(r -> r["Bus ID"] == 101, eachrow(bus)))

    load = only(
        filter(
            c -> c.name == row["Bus Name"],
            PowerOpenAPIModels.get_components(doc, "PowerLoad"),
        ),
    )
    @test load.active_power == Float64(row["MW Load"])
    @test load.max_active_power == Float64(row["MW Load"])
    @test load.reactive_power == Float64(row["MVAR Load"])
    @test load.max_reactive_power == Float64(row["MVAR Load"])
    @test load.base_power == 100.0
    @test load.power_units == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
    @test load.conformity == PowerOpenAPIModels.LoadConformity("UNDEFINED")
end

@testset "reserves seven products with minute units" begin
    doc, src, reserve_ids = _demand_built_case()
    reserves = CSV.read(joinpath(src, "reserves.csv"), DataFrame)

    @test nrow(reserves) == 7
    @test Set(keys(reserve_ids)) == Set(reserves[!, "Reserve Product"])
    @test length(PowerOpenAPIModels.get_components(doc, "OnlineReserve")) == 7

    by_name = Dict(
        c.name => c for c in PowerOpenAPIModels.get_components(doc, "OnlineReserve")
    )

    spin1 = by_name["Spin_Up_R1"]
    @test spin1.time_frame == 10.0
    @test spin1.sustained_time == 60.0
    @test spin1.requirement ≈ 40.413
    @test spin1.reserve_direction == PowerOpenAPIModels.ReserveDirection("UP")

    flex_up = by_name["Flex_Up"]
    @test flex_up.time_frame == 20.0
    @test flex_up.sustained_time == 60.0
    @test flex_up.reserve_direction == PowerOpenAPIModels.ReserveDirection("UP")

    flex_down = by_name["Flex_Down"]
    @test flex_down.reserve_direction == PowerOpenAPIModels.ReserveDirection("DOWN")

    reg_up = by_name["Reg_Up"]
    @test reg_up.time_frame == 5.0
    @test reg_up.sustained_time == 60.0

    for name in ("Spin_Up_R1", "Spin_Up_R2", "Spin_Up_R3", "Flex_Up", "Flex_Down", "Reg_Up", "Reg_Down")
        comp = by_name[name]
        @test comp.max_output_fraction == 1.0
        @test comp.max_participation_factor == 1.0
        @test comp.deployed_fraction == 0.0
        @test comp.available == true
    end

    PowerOpenAPIModels.validate_document(doc)
end

@testset "service association counts per product" begin
    doc, src, reserve_ids = _demand_built_case()

    reserve_name_by_id = Dict(v => k for (k, v) in reserve_ids)
    counts = Dict(name => 0 for name in keys(reserve_ids))
    for assoc in doc.service_associations
        name = reserve_name_by_id[assoc.service_id]
        counts[name] += 1
    end

    expected = Dict(
        "Spin_Up_R1" => 34,
        "Spin_Up_R2" => 25,
        "Spin_Up_R3" => 43,
        "Flex_Up" => 102,
        "Flex_Down" => 102,
        "Reg_Up" => 102,
        "Reg_Down" => 102,
    )
    @test counts == expected
    @test sum(values(counts)) == 510
    @test length(doc.service_associations) == 510

    PowerOpenAPIModels.validate_document(doc)
end
