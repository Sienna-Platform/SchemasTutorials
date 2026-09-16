@testset "investments source data" begin
    src = RTSGMLCCase.investments_source_dir()
    for name in RTSGMLCCase.REQUIRED_INVESTMENTS_FILES
        @test isfile(joinpath(src, name))
    end
end

@testset "investments source dir matches exactly the 16 required files" begin
    src = RTSGMLCCase.investments_source_dir()
    on_disk = Set{String}()
    for (root, _, files) in walkdir(src)
        for file in files
            push!(on_disk, relpath(joinpath(root, file), src))
        end
    end
    @test on_disk == Set(RTSGMLCCase.REQUIRED_INVESTMENTS_FILES)
end

@testset "missing investments directory raises without downloading" begin
    mktempdir() do repo_root
        err = nothing
        try
            RTSGMLCCase.investments_source_dir(repo_root)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        @test occursin("does not exist", message)
    end
end

@testset "partial investments directory raises with missing names" begin
    mktempdir() do repo_root
        root = joinpath(repo_root, "data", "RTS-investments")
        mkpath(joinpath(root, "capacitydata"))
        write(joinpath(root, "hierarchy_rts.csv"), "")
        write(joinpath(root, "scalars.csv"), "")

        err = nothing
        try
            RTSGMLCCase.investments_source_dir(repo_root)
        catch caught
            err = caught
        end
        @test err !== nothing
        message = sprint(showerror, err)
        present = Set(["hierarchy_rts.csv", "scalars.csv"])
        for name in RTSGMLCCase.REQUIRED_INVESTMENTS_FILES
            name in present && continue
            @test occursin(name, message)
        end
    end
end
