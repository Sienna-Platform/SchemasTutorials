@testset "source data" begin
    src = RTSGMLCCase.rts_source_dir()
    for name in RTSGMLCCase.REQUIRED_SOURCE_TABLES
        @test isfile(joinpath(src, RTSGMLCCase.SOURCE_DATA, name))
    end
    @test isdir(joinpath(src, RTSGMLCCase.TIMESERIES_DATA))
end

@testset "partial cache raises with missing names" begin
    mktempdir() do repo_root
        source_data = joinpath(repo_root, "data", "RTS-GMLC", "RTS_Data", RTSGMLCCase.SOURCE_DATA)
        mkpath(source_data)
        write(joinpath(source_data, "bus.csv"), "")

        err = nothing
        try
            RTSGMLCCase.rts_source_dir(repo_root)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        for name in
            ("branch.csv", "gen.csv", "dc_branch.csv", "reserves.csv", "storage.csv", "timeseries_pointers.csv")
            @test occursin(name, message)
        end
        @test occursin(RTSGMLCCase.TIMESERIES_DATA, message)
    end
end
