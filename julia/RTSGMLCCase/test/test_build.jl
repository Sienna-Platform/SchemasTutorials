# Task 9: the driver. Builds the whole RTS-GMLC case end to end, reads it back, and proves the
# build is deterministic and complete.
#
# The expensive full build (all 282 time-series profiles, some ~105k rows) runs once, shared
# across every testset below that only needs to *read* the built case -- mirroring the Python
# suite's module-scoped fixture. The determinism test additionally runs a second full build,
# since byte-identity across two independent builds is the whole point.

const _BUILD_CASE_DIR = mktempdir()
const _BUILD_DOC = RTSGMLCCase.build_case(_BUILD_CASE_DIR)

const EXPECTED_COMPONENT_COUNTS = Dict(
    "ACBus" => 73,
    "Area" => 3,
    "LoadZone" => 21,
    "FixedAdmittance" => 3,
    "Arc" => 109,
    "Line" => 105,
    "TransformerCircuit" => 15,
    "TwoWindingTransformer" => 15,
    "TwoTerminalGenericHVDCLine" => 1,
    "PowerLoad" => 51,
    "ThermalStandard" => 73,
    "RenewableDispatch" => 30,
    "RenewableNonDispatch" => 31,
    "HydroDispatch" => 20,
    "SynchronousCondenser" => 3,
    "EnergyReservoirStorage" => 1,
    "OnlineReserve" => 7,
)
const EXPECTED_SERVICE_ASSOCIATIONS = 510
const EXPECTED_TIME_SERIES_ASSOCIATIONS = 282

@testset "build_case produces expected component counts" begin
    counts = Dict(
        name => length(PowerOpenAPIModels.get_components(_BUILD_DOC, name)) for
        name in PowerOpenAPIModels.component_type_names(_BUILD_DOC)
    )
    @test counts == EXPECTED_COMPONENT_COUNTS
    @test length(_BUILD_DOC.service_associations) == EXPECTED_SERVICE_ASSOCIATIONS
    @test length(_BUILD_DOC.time_series_associations) == EXPECTED_TIME_SERIES_ASSOCIATIONS
    @test isfile(joinpath(_BUILD_CASE_DIR, "system.json"))
end

@testset "id uniqueness across the whole document" begin
    owner_by_id = Dict{Int, String}()
    for type_name in PowerOpenAPIModels.component_type_names(_BUILD_DOC)
        for item in PowerOpenAPIModels.get_components(_BUILD_DOC, type_name)
            @test !haskey(owner_by_id, item.id)
            owner_by_id[item.id] = type_name
        end
    end
end

@testset "round trip components match bucket by bucket" begin
    read_doc = RTSGMLCCase.read_case(_BUILD_CASE_DIR)

    built_names = Set(PowerOpenAPIModels.component_type_names(_BUILD_DOC))
    read_names = Set(PowerOpenAPIModels.component_type_names(read_doc))
    @test built_names == read_names

    for type_name in sort(collect(built_names))
        built_items = PowerOpenAPIModels.get_components(_BUILD_DOC, type_name)
        read_items = PowerOpenAPIModels.get_components(read_doc, type_name)
        @test length(built_items) == length(read_items)
        built_json = [PowerOpenAPIModels.encode(c) for c in built_items]
        read_json = [PowerOpenAPIModels.encode(c) for c in read_items]
        @test built_json == read_json
    end
end

@testset "sidecar has no orphans and lengths match row counts" begin
    assocs = [assoc.value for assoc in _BUILD_DOC.time_series_associations]
    seen_paths = Set{String}()
    for assoc in assocs
        path = joinpath(_BUILD_CASE_DIR, assoc.uri)
        @test isfile(path)
        push!(seen_paths, path)
        df = DataFrame(Parquet2.Dataset(path); copycols = true)
        @test nrow(df) == assoc.length
    end

    on_disk = Set(
        joinpath(_BUILD_CASE_DIR, "timeseries", f) for
        f in readdir(joinpath(_BUILD_CASE_DIR, "timeseries")) if endswith(f, ".parquet")
    )
    @test on_disk == seen_paths
    @test length(on_disk) < EXPECTED_TIME_SERIES_ASSOCIATIONS
end

@testset "build is byte deterministic" begin
    case_dir_b = mktempdir()
    RTSGMLCCase.build_case(case_dir_b)

    bytes_a = read(joinpath(_BUILD_CASE_DIR, "system.json"))
    bytes_b = read(joinpath(case_dir_b, "system.json"))
    @test bytes_a == bytes_b
end

# --- fast: CLI argument handling needs no RTS data or build -----------------

@testset "cli reports usage error without output dir" begin
    package_root = dirname(dirname(pathof(RTSGMLCCase)))
    build_rts_path = joinpath(package_root, "build_rts.jl")
    cmd = `julia --project=$package_root $build_rts_path`

    buffer = IOBuffer()
    process = run(pipeline(ignorestatus(cmd); stdout = buffer, stderr = buffer))
    output = String(take!(buffer))

    @test process.exitcode == 2
    @test occursin("usage", lowercase(output))
end
