#!/usr/bin/env julia
# CLI: build the full RTS-GMLC case into the given output directory.
#
# Usage:
#
#     julia --project=. build_rts.jl <output-dir>

using RTSGMLCCase
using PowerOpenAPIModels

function main(argv::Vector{String})
    if length(argv) != 1
        println(stderr, "usage: julia build_rts.jl <output-dir>")
        return 2
    end

    case_dir = argv[1]
    doc = RTSGMLCCase.build_case(case_dir)

    println("wrote case to $case_dir")
    println("component counts:")
    for type_name in PowerOpenAPIModels.component_type_names(doc)
        count = length(PowerOpenAPIModels.get_components(doc, type_name))
        println("  $type_name: $count")
    end
    println("service_associations: $(length(doc.service_associations))")
    println("time_series_associations: $(length(doc.time_series_associations))")

    parquet_files = filter(
        f -> endswith(f, ".parquet"),
        readdir(joinpath(case_dir, "timeseries")),
    )
    println("parquet files: $(length(parquet_files))")

    return 0
end

exit(main(ARGS))
