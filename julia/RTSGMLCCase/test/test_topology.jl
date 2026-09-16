@testset "topology counts and fields from source" begin
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    bus = CSV.read(joinpath(src, "bus.csv"), DataFrame)

    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)

    n_areas = length(unique(bus[!, "Area"]))
    n_zones = length(unique(bus[!, "Zone"]))

    @test length(PowerOpenAPIModels.get_components(doc, "ACBus")) == nrow(bus)
    @test length(PowerOpenAPIModels.get_components(doc, "Area")) == n_areas
    @test length(PowerOpenAPIModels.get_components(doc, "LoadZone")) == n_zones

    # Pinned expected totals (CAMPAIGN-FACTS.md "Expected component counts").
    @test length(PowerOpenAPIModels.get_components(doc, "ACBus")) == 73
    @test length(PowerOpenAPIModels.get_components(doc, "Area")) == 3
    @test length(PowerOpenAPIModels.get_components(doc, "LoadZone")) == 21
    @test length(PowerOpenAPIModels.get_components(doc, "FixedAdmittance")) == 3

    abel = only(filter(c -> c.number == 101, PowerOpenAPIModels.get_components(doc, "ACBus")))
    @test abel.name == "Abel"
    expected_angle = deg2rad(only(bus[bus[!, "Bus ID"].==101, "V Angle"]))
    @test isapprox(abel.angle, expected_angle; atol = 1e-12)
    @test abel.voltage_limits.min == 0.95
    @test abel.voltage_limits.max == 1.05
    @test abel.available == true

    # R18: ACBusType is an unenforced String alias in Julia — assert the emitted literal
    # explicitly rather than trusting construction to reject a misspelling.
    ref_buses = filter(c -> c.bustype == PowerOpenAPIModels.ACBusType("REF"), PowerOpenAPIModels.get_components(doc, "ACBus"))
    @test length(ref_buses) >= 1

    # R3: three buses (106 Alber, 206 Bajer, 306 Camus) carry a nonzero `MVAR Shunt B` and
    # get a `FixedAdmittance` each rather than being silently dropped.
    shunts = PowerOpenAPIModels.get_components(doc, "FixedAdmittance")
    @test Set(s.name for s in shunts) == Set(["Alber_shunt", "Bajer_shunt", "Camus_shunt"])
    for shunt in shunts
        @test shunt.y.real == 0.0
        @test shunt.y.imag == -100.0
        @test shunt.admittance_units ==
              PowerOpenAPIModels.ShuntAdmittanceUnitBasis("NATURAL_UNITS")
    end

    # R24: `peak_active_power`/`peak_reactive_power` are derived sums over member buses, not 0.0.
    area_load = combine(
        groupby(bus, "Area"),
        "MW Load" => sum => :mw,
        "MVAR Load" => sum => :mvar,
    )
    area_mw = Dict(row["Area"] => row.mw for row in eachrow(area_load))
    area_mvar = Dict(row["Area"] => row.mvar for row in eachrow(area_load))
    for area in PowerOpenAPIModels.get_components(doc, "Area")
        area_value = parse(Int, area.name)
        @test area.peak_active_power == area_mw[area_value]
        @test area.peak_reactive_power == area_mvar[area_value]
        @test area.peak_active_power != 0.0
        @test area.load_response == 0.0
    end
    total_system_load = sum(bus[!, "MW Load"])
    @test Set(a.peak_active_power for a in PowerOpenAPIModels.get_components(doc, "Area")) ==
          Set([total_system_load / n_areas])
    @test only(unique(a.peak_active_power for a in PowerOpenAPIModels.get_components(doc, "Area")))==2850.0

    zone_load = combine(
        groupby(bus, "Zone"),
        "MW Load" => sum => :mw,
        "MVAR Load" => sum => :mvar,
    )
    zone_mw = Dict(row["Zone"] => row.mw for row in eachrow(zone_load))
    zone_mvar = Dict(row["Zone"] => row.mvar for row in eachrow(zone_load))
    zone_peak_active_sum = 0.0
    for zone in PowerOpenAPIModels.get_components(doc, "LoadZone")
        zone_value = parse(Float64, zone.name)
        @test zone.peak_active_power == zone_mw[zone_value]
        @test zone.peak_reactive_power == zone_mvar[zone_value]
        @test zone.peak_active_power != 0.0
        zone_peak_active_sum += zone.peak_active_power
    end
    @test zone_peak_active_sum == total_system_load

    @test Set(keys(idx.bus_id_by_number)) == Set(bus[!, "Bus ID"])
    @test Set(keys(idx.area_id_by_name)) == Set(string(Int(a)) for a in unique(bus[!, "Area"]))
    @test Set(keys(idx.zone_id_by_name)) == Set(string(Int(z)) for z in unique(bus[!, "Zone"]))

    # Areas and zones were added in sorted order — ids increase with name.
    sorted_area_ids =
        [idx.area_id_by_name[name] for name in sort(collect(keys(idx.area_id_by_name)); by = x -> parse(Int, x))]
    @test issorted(sorted_area_ids)
    sorted_zone_ids =
        [idx.zone_id_by_name[name] for name in sort(collect(keys(idx.zone_id_by_name)); by = x -> parse(Int, x))]
    @test issorted(sorted_zone_ids)

    PowerOpenAPIModels.validate_document(doc)
end
