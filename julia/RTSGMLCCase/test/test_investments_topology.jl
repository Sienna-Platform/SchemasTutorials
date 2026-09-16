# The investments topology stage adds nothing to the document.
#
# SiennaSchemas 0.1.0 defines no `Node` and no `Zone`, so all the stage can do is hand back the
# operations ids later stages point their `region` fields at. These tests assert exactly that:
# the portfolio stays empty, and every id in the returned index resolves to an `ACBus` or `Area`
# in the base system.

function _build_investments(doc)
    op_src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    idx = RTSGMLCCase.add_topology!(doc, op_src)
    portfolio = RTSGMLCCase.new_portfolio(
        doc;
        aggregation = "Area",
        base_system_file = RTSGMLCCase.SYSTEM_FILENAME,
    )
    inv_src = RTSGMLCCase.investments_source_dir()
    inv_idx = RTSGMLCCase.add_investment_topology!(portfolio, inv_src, idx)
    return portfolio, idx, inv_idx
end

@testset "investment topology adds nothing to the document" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx = _build_investments(doc)

    # No Node, no Zone, and no TopologyMapping: the schema has no investments topology
    # component, and the bus/area membership is already on `ACBus.area`.
    @test isempty(PowerOpenAPIModels.component_type_names(portfolio.document))
    @test isempty(portfolio.document.supplemental_attributes)
    @test isempty(portfolio.document.supplemental_attribute_associations)

    PowerOpenAPIModels.validate_document(doc)
    PowerOpenAPIModels.validate_document(portfolio.document)
end

@testset "node ids are the operations ACBus ids" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx = _build_investments(doc)
    bus = CSV.read(
        joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA, "bus.csv"),
        DataFrame,
    )

    @test inv_idx.node_id_by_bus_number == idx.bus_id_by_number
    @test Set(keys(inv_idx.node_id_by_bus_number)) == Set(Int.(bus[!, "Bus ID"]))
    @test length(inv_idx.node_id_by_bus_number) == 73

    buses = PowerOpenAPIModels.get_components(doc, "ACBus")
    abel = only(b for b in buses if b.id == inv_idx.node_id_by_bus_number[101])
    @test abel.name == "Abel"
    @test abel.bustype == PowerOpenAPIModels.ACBusType("PV")
end

@testset "zone membership is readable from ACBus.area alone" begin
    # What the dropped TopologyMapping would have restated: every bus already names its zone,
    # in the base system, via `ACBus.area`.
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx = _build_investments(doc)

    for b in PowerOpenAPIModels.get_components(doc, "ACBus")
        @test inv_idx.zone_id_by_bus_number[b.number] == b.area
    end
end

@testset "zones are the 3 RTS areas not the 5 ReEDS bas" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx = _build_investments(doc)

    @test inv_idx.zone_id_by_name == idx.area_id_by_name
    @test Set(keys(inv_idx.zone_id_by_name)) == Set(["1", "2", "3"])

    area_names = Set(a.name for a in PowerOpenAPIModels.get_components(doc, "Area"))
    @test area_names == Set(["1", "2", "3"])

    hierarchy = CSV.read(
        joinpath(RTSGMLCCase.investments_source_dir(), "hierarchy_rts.csv"),
        DataFrame,
    )
    ba_codes = Set(String.(unique(hierarchy[!, "ba"])))
    @test length(ba_codes) == 5
    @test isempty(intersect(Set(keys(inv_idx.zone_id_by_name)), ba_codes))
end

@testset "zone_id_by_bus_number maps every bus to its area" begin
    doc = RTSGMLCCase.new_document()
    portfolio, idx, inv_idx = _build_investments(doc)
    bus = CSV.read(
        joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA, "bus.csv"),
        DataFrame,
    )

    @test Set(keys(inv_idx.zone_id_by_bus_number)) == Set(Int.(bus[!, "Bus ID"]))
    for row in eachrow(bus)
        expected = idx.area_id_by_name[string(Int(row["Area"]))]
        @test inv_idx.zone_id_by_bus_number[Int(row["Bus ID"])] == expected
    end
end
