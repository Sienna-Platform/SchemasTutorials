using Test
using RTSGMLCCase
using PowerOpenAPIModels
using PowerOperationsOpenAPIModels
using CSV
using DataFrames
using Dates
using TimeZones
using Parquet2

@testset "RTSGMLCCase" begin
    include("test_data.jl")
    include("test_document.jl")
    include("test_topology.jl")
    include("test_investments_data.jl")
    include("test_investments_topology.jl")
    include("test_investments_demand.jl")
    include("test_investments_costs.jl")
    include("test_investments_technologies.jl")
    include("test_investments_storage.jl")
    include("test_investments_transport.jl")
    include("test_investments_policy.jl")
    include("test_branches.jl")
    include("test_generation.jl")
    include("test_demand.jl")
    include("test_sidecar.jl")
    include("test_timeseries.jl")
    include("test_build.jl")
end
