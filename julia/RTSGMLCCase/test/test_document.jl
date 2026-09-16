@testset "document basics" begin
    doc = RTSGMLCCase.new_document()

    area = PowerOpenAPIModels.Area(;
        id = PowerOpenAPIModels.next_id!(doc),
        name = "1",
        base_power = 100.0,
        power_units = PowerOpenAPIModels.UnitSystem("NATURAL_UNITS"),
    )
    area_id = RTSGMLCCase.add!(doc, area)

    @test area_id == 1
    @test area.id == area_id
    @test area.power_units == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
    @test length(PowerOpenAPIModels.get_components(doc, "Area")) == 1
    PowerOpenAPIModels.validate_document(doc)
end

@testset "an enum field rejects a value outside its listed set" begin
    # The generated enums are real types in both languages now, so a typo fails at
    # construction instead of riding into the document as a bare string.
    @test_throws ArgumentError PowerOpenAPIModels.UnitSystem("natural_units")
    @test_throws ArgumentError PowerOpenAPIModels.ACBusType("ref ")
end

@testset "add! keeps a caller-supplied id and does not touch the counter" begin
    doc = RTSGMLCCase.new_document()
    area = PowerOpenAPIModels.Area(;
        id = 7,
        name = "preset",
        base_power = 100.0,
        power_units = PowerOpenAPIModels.UnitSystem("NATURAL_UNITS"),
    )

    @test RTSGMLCCase.add!(doc, area) == 7
    # the counter never advanced to mint the id above, so the next mint is still 1
    @test PowerOpenAPIModels.next_id!(doc) == 1
end

@testset "interrogating a document" begin
    doc = RTSGMLCCase.new_document()
    for name in ("1", "2")
        RTSGMLCCase.add!(
            doc,
            PowerOpenAPIModels.Area(;
                id = PowerOpenAPIModels.next_id!(doc),
                name = name,
                base_power = 100.0,
                power_units = PowerOpenAPIModels.UnitSystem("NATURAL_UNITS"),
            ),
        )
    end

    @test Set(PowerOpenAPIModels.component_type_names(doc)) == Set(["Area"])
    @test length(PowerOpenAPIModels.get_components(doc, "Area")) == 2
    @test isempty(PowerOpenAPIModels.get_components(doc, "ACBus"))
    @test PowerOpenAPIModels.get_time_series_storage_file(doc) == "timeseries"
end
