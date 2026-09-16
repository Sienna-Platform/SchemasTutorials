@testset "generation counts match gen.csv groupby" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    gen = CSV.read(joinpath(src, "gen.csv"), DataFrame)

    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    ids = RTSGMLCCase.add_generation!(doc, src, idx)

    # Every Unit Type in the source is covered by the table (ROR included -- 12, not 11).
    @test Set(gen[!, "Unit Type"]) == Set(keys(RTSGMLCCase.UNIT_TYPE_TO_TARGET))
    @test length(RTSGMLCCase.UNIT_TYPE_TO_TARGET) == 12

    # Counts derived from a fresh group-by, not copied from the mapping.
    counts = combine(groupby(gen, "Unit Type"), nrow => :n)
    expected_by_target = Dict{String, Int}()
    for row in eachrow(counts)
        target = RTSGMLCCase.UNIT_TYPE_TO_TARGET[row["Unit Type"]]
        expected_by_target[target] = get(expected_by_target, target, 0) + row.n
    end
    for (target, expected) in expected_by_target
        @test length(PowerOpenAPIModels.get_components(doc, target)) == expected
    end

    # Pinned totals.
    @test length(PowerOpenAPIModels.get_components(doc, "ThermalStandard")) == 73
    @test length(PowerOpenAPIModels.get_components(doc, "RenewableDispatch")) == 30
    @test length(PowerOpenAPIModels.get_components(doc, "RenewableNonDispatch")) == 31
    @test length(PowerOpenAPIModels.get_components(doc, "HydroDispatch")) == 20
    @test length(PowerOpenAPIModels.get_components(doc, "SynchronousCondenser")) == 3
    @test length(PowerOpenAPIModels.get_components(doc, "EnergyReservoirStorage")) == 1

    @test length(ids) == nrow(gen) == 158
    thermal_ids = Set(c.id for c in PowerOpenAPIModels.get_components(doc, "ThermalStandard"))
    @test ids["101_CT_1"] in thermal_ids

    PowerOpenAPIModels.validate_document(doc)
end

@testset "ct1 thermal cost and ratings" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)

    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    RTSGMLCCase.add_generation!(doc, src, idx)

    thermals = PowerOpenAPIModels.get_components(doc, "ThermalStandard")
    unit = only(filter(t -> t.name == "101_CT_1", thermals))

    @test unit.base_power == 24.0
    @test unit.rating == 22.360679774997898
    @test unit.time_limits.up == 60.0
    @test unit.time_limits.down == 60.0
    @test unit.fuel == PowerOpenAPIModels.ThermalFuels("DISTILLATE_FUEL_OIL")
    @test unit.prime_mover_type == PowerOpenAPIModels.PrimeMovers("CT")

    cost = unit.operation_cost.value
    @test cost.cost_type == "THERMAL"
    @test cost.shut_down == 0.0
    @test cost.start_up.value == 51.747

    fuel_curve = cost.variable_operation_cost.value
    @test fuel_curve.variable_cost_type == "FUEL"
    @test fuel_curve.fuel_cost == 0.0103494

    value_curve = fuel_curve.value_curve.value
    @test value_curve.curve_type == "INCREMENTAL"
    function_data = value_curve.function_data.value
    @test function_data.function_type == "PIECEWISE_STEP"
    @test function_data.x_coords == [8.0, 12.0, 16.0, 20.0]
    @test function_data.y_coords == [9456.0, 9476.0, 10352.0]
    @test value_curve.initial_input == 104912.0

    # R18-equivalent: these are plain Strings in Julia, unlike Python's enforced enum -- assert
    # the emitted literal directly so a misspelling can't slip through unnoticed.
    @test unit.status == PowerOpenAPIModels.OperationalStates("ONLINE")
    @test unit.commitment_mode == PowerOpenAPIModels.CommitmentModes("COMMITTED")
    @test unit.power_units == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
    @test fuel_curve.power_units == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")

    PowerOpenAPIModels.validate_document(doc)
end

@testset "renewable and hydro ratings and conventions" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    gen = CSV.read(joinpath(src, "gen.csv"), DataFrame)

    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    RTSGMLCCase.add_generation!(doc, src, idx)

    # RenewableDispatch/RenewableNonDispatch: rating == base_power == Base MVA == PMax MW.
    for target in ("RenewableDispatch", "RenewableNonDispatch")
        for comp in PowerOpenAPIModels.get_components(doc, target)
            @test comp.rating == comp.base_power
        end
    end

    # HydroDispatch: rating is hypot(PMax, QMax), not Base MVA.
    ror = only(
        filter(
            c -> c.name == "201_HYDRO_4",
            PowerOpenAPIModels.get_components(doc, "HydroDispatch"),
        ),
    )
    @test ror.rating == 52.49761899362675
    @test ror.base_power == 53.0
    @test ror.prime_mover_type == PowerOpenAPIModels.PrimeMovers("HY")

    # SynchronousCondenser: rating == QMax MVAR, base_power hardcoded to 100.0, no
    # prime_mover_type field at all.
    for comp in PowerOpenAPIModels.get_components(doc, "SynchronousCondenser")
        row = only(filter(r -> r["GEN UID"] == comp.name, eachrow(gen)))
        @test comp.rating == Float64(row["QMax MVAR"])
        @test comp.base_power == 100.0
        @test !hasproperty(comp, :prime_mover_type)
    end

    # EnergyReservoirStorage: rating from storage.csv Rating MVA; efficiency from the source's
    # real 85% roundtrip figure, split as sqrt(0.85) per leg, not the reference case's 1.0/1.0.
    storage = only(PowerOpenAPIModels.get_components(doc, "EnergyReservoirStorage"))
    @test storage.rating == 50.0
    @test storage.efficiency.in ≈ sqrt(0.85)
    @test storage.efficiency.out ≈ sqrt(0.85)

    PowerOpenAPIModels.validate_document(doc)
end

@testset "unmapped unit type raises naming the row" begin
    mktempdir() do dir
        write(
            joinpath(dir, "gen.csv"),
            "GEN UID,Bus ID,Unit Type\n999_BOGUS_1,101,NOT_A_REAL_TYPE\n",
        )
        write(
            joinpath(dir, "storage.csv"),
            "GEN UID,Storage,Max Volume GWh,Initial Volume GWh," *
            "Start Energy,Inflow Limit GWh,Rating MVA,position\n",
        )
        doc = RTSGMLCCase.new_document()
        idx = RTSGMLCCase.TopologyIndex(Dict{Int, Int}(), Dict{String, Int}(), Dict{String, Int}())

        err = try
            RTSGMLCCase.add_generation!(doc, dir, idx)
            nothing
        catch e
            e
        end
        @test err isa ErrorException
        @test occursin("999_BOGUS_1", err.msg)
        @test occursin("NOT_A_REAL_TYPE", err.msg)
    end
end

@testset "thermal unmapped fuel raises" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    gen = CSV.read(joinpath(src, "gen.csv"), DataFrame)
    bad = gen[gen[!, "GEN UID"] .== "101_CT_1", :]
    bad[1, "Fuel"] = "Bogus"
    row = only(eachrow(bad))

    doc = RTSGMLCCase.new_document()
    err = try
        RTSGMLCCase._build_thermal_standard(doc, row, 1, nothing)
        nothing
    catch e
        e
    end
    @test err isa ErrorException
    @test occursin("101_CT_1", err.msg)
    @test occursin("Bogus", err.msg)
end
