@testset "branch partition and arcs" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    branch = CSV.read(joinpath(src, "branch.csv"), DataFrame)
    dc_branch = CSV.read(joinpath(src, "dc_branch.csv"), DataFrame)
    bus = CSV.read(joinpath(src, "bus.csv"), DataFrame)
    base_kv = Dict(Int(row["Bus ID"]) => Float64(row["BaseKV"]) for row in eachrow(bus))

    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    RTSGMLCCase.add_branches!(doc, src, idx)

    # Two independent classification rules must agree exactly (R21).
    tr_ratio_rule = [!(Float64(t) in (0.0, 1.0)) for t in branch[!, "Tr Ratio"]]
    voltage_rule = [
        base_kv[Int(row["From Bus"])] != base_kv[Int(row["To Bus"])] for row in eachrow(branch)
    ]
    @test tr_ratio_rule == voltage_rule
    n_xf = count(tr_ratio_rule)

    lines = PowerOpenAPIModels.get_components(doc, "Line")
    circuits = PowerOpenAPIModels.get_components(doc, "TransformerCircuit")
    transformers = PowerOpenAPIModels.get_components(doc, "TwoWindingTransformer")
    hvdc_lines = PowerOpenAPIModels.get_components(doc, "TwoTerminalGenericHVDCLine")
    arcs = PowerOpenAPIModels.get_components(doc, "Arc")

    @test length(lines) == nrow(branch) - n_xf
    @test length(circuits) == n_xf
    @test length(transformers) == n_xf

    # Pinned expected totals (CAMPAIGN-FACTS.md "Expected component counts", R21).
    @test length(lines) == 105
    @test length(circuits) == 15
    @test length(transformers) == 15
    @test length(hvdc_lines) == 1

    # No `TransformerCircuit` carries a `name` -- the name lives on `TwoWindingTransformer`.
    for circuit in circuits
        @test circuit.arc in [a.id for a in arcs]
    end
    for line in lines
        @test line.arc in [a.id for a in arcs]
    end
    xf_names = Set(t.name for t in transformers)
    xf_uids = Set(String(u) for u in branch[tr_ratio_rule, "UID"])
    @test xf_names == xf_uids

    ac_pairs = Set(
        (idx.bus_id_by_number[Int(row["From Bus"])], idx.bus_id_by_number[Int(row["To Bus"])])
        for row in eachrow(branch)
    )
    dc_pairs = Set(
        (idx.bus_id_by_number[Int(row["From Bus"])], idx.bus_id_by_number[Int(row["To Bus"])])
        for row in eachrow(dc_branch)
    )
    @test length(ac_pairs) == 108
    @test length(dc_pairs) == 1
    arc_pairs = [(a.from_id, a.to_id) for a in arcs]
    @test length(Set(arc_pairs)) == length(arc_pairs) # deduplicated
    @test length(union(ac_pairs, dc_pairs)) == length(arcs)
    @test length(arcs) == 109

    # The arc allocator genuinely reuses ids for a known duplicated ordered pair (12 branch.csv
    # rows share their (From Bus, To Bus) with another row) rather than merely landing on the
    # right final count by coincidence.
    a25_1 = only(filter(l -> l.name == "A25-1", lines))
    a25_2 = only(filter(l -> l.name == "A25-2", lines))
    @test a25_1.arc == a25_2.arc

    hvdc = only(hvdc_lines)
    @test hvdc.name == "DC1"
    @test hvdc.active_power_limits_from.min == -100.0
    @test hvdc.active_power_limits_from.max == 100.0
    @test hvdc.active_power_limits_to.min == -100.0
    @test hvdc.active_power_limits_to.max == 100.0
    @test hvdc.reactive_power_limits_from.min == 0.0
    @test hvdc.reactive_power_limits_from.max == 100.0
    @test hvdc.reactive_power_limits_to.min == 0.0
    @test hvdc.reactive_power_limits_to.max == 100.0
    @test hvdc.loss.value_curve.value.function_data.value.proportional_term == 0.1

    PowerOpenAPIModels.validate_document(doc)
end

@testset "line A1 spot check" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    RTSGMLCCase.add_branches!(doc, src, idx)

    a1 = only(filter(l -> l.name == "A1", PowerOpenAPIModels.get_components(doc, "Line")))
    @test a1.r == 0.003
    @test a1.x == 0.014
    @test a1.b.from == 0.2305
    @test a1.b.to == 0.2305
    @test a1.rating == 175.0
    @test a1.rating_b == 193.0
    @test a1.rating_c == 200.0
    @test a1.base_power == 100.0
    # R18: power_units/parameter_units are unenforced String aliases in Julia -- assert the
    # emitted literal explicitly.
    @test a1.power_units == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
    @test a1.parameter_units == PowerOpenAPIModels.ImpedanceUnitBasis("COMPONENT_BASE")
    @test a1.angle_limits.min == -3.1416
    @test a1.angle_limits.max == 3.1416
end
