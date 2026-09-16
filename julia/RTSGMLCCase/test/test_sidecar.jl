const _SIDECAR_HASH_RE = r"^[0-9a-f]{64}$"

function _sidecar_timestamps(n::Int)
    return [ZonedDateTime(Dates.DateTime(2020, 1, 1), tz"UTC") + Dates.Hour(i) for i in 0:(n - 1)]
end

@testset "pinned cross-language hash" begin
    # Controller-verified literal, confirmed directly against Python's
    # `rts_gmlc_case.sidecar.data_hash(np.array([1.0, 2.0, 3.0]))`.
    @test RTSGMLCCase.data_hash([1.0, 2.0, 3.0]) ==
          "a68de4b5e96a60c8ceb3c7b7ef93461725bdbbff3516b136585a743b5c0ec664"
end

@testset "hash is 64 lowercase hex chars" begin
    @test occursin(_SIDECAR_HASH_RE, RTSGMLCCase.data_hash([1.0, 2.0, 3.0]))
end

@testset "integer input hashes as float64" begin
    int_hash = RTSGMLCCase.data_hash(Float64.([1, 2, 3]))
    float_hash = RTSGMLCCase.data_hash([1.0, 2.0, 3.0])
    @test int_hash == float_hash
end

@testset "dedup same values twice yields one file same uri" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        values = [1.0, 2.0, 3.0]
        timestamps = _sidecar_timestamps(3)

        uri1, hash1 = RTSGMLCCase.write_series!(writer, timestamps, values)
        uri2, hash2 = RTSGMLCCase.write_series!(writer, timestamps, values)

        @test uri1 == uri2
        @test hash1 == hash2
        @test occursin(_SIDECAR_HASH_RE, hash1)

        files = filter(f -> endswith(f, ".parquet"), readdir(joinpath(dir, "timeseries")))
        @test length(files) == 1
        @test uri1 == "timeseries/ts_$(hash1[1:16]).parquet"
    end
end

@testset "distinct values yield distinct files" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        timestamps = _sidecar_timestamps(3)

        uri1, hash1 = RTSGMLCCase.write_series!(writer, timestamps, [1.0, 2.0, 3.0])
        uri2, hash2 = RTSGMLCCase.write_series!(writer, timestamps, [4.0, 5.0, 6.0])

        @test uri1 != uri2
        @test hash1 != hash2

        files = filter(f -> endswith(f, ".parquet"), readdir(joinpath(dir, "timeseries")))
        @test length(files) == 2
    end
end

@testset "round trip values and timestamp type" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        values = [1.5, 2.5, 3.5]
        timestamps = _sidecar_timestamps(3)

        uri, _ = RTSGMLCCase.write_series!(writer, timestamps, values)

        df = DataFrame(Parquet2.Dataset(joinpath(dir, uri)); copycols = true)
        @test eltype(df.timestamp) == Dates.DateTime
        @test eltype(df.value) == Float64
        @test df.value == values
        @test df.timestamp == Dates.DateTime.(timestamps)
    end
end

@testset "write returns uri relative to case dir" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        uri, hash_value = RTSGMLCCase.write_series!(writer, _sidecar_timestamps(3), [9.0, 8.0, 7.0])
        @test startswith(uri, "timeseries/ts_")
        @test endswith(uri, ".parquet")
        @test occursin(hash_value[1:16], uri)
    end
end

@testset "corrupt file at hash path is replaced" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        values = [1.0, 2.0, 3.0]
        timestamps = _sidecar_timestamps(3)

        digest = RTSGMLCCase.data_hash(values)
        corrupt_path = joinpath(dir, "timeseries", "ts_$(digest[1:16]).parquet")
        mkpath(dirname(corrupt_path))
        write(corrupt_path, "not a parquet file")

        uri, returned_hash = RTSGMLCCase.write_series!(writer, timestamps, values)

        @test returned_hash == digest
        df = DataFrame(Parquet2.Dataset(joinpath(dir, uri)); copycols = true)
        @test df.value == values
    end
end

@testset "non-UTC timestamps convert to the correct instant" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        eastern = [
            ZonedDateTime(Dates.DateTime(2020, 1, 1), tz"America/New_York") + Dates.Hour(i) for
            i in 0:2
        ]
        values = [1.0, 2.0, 3.0]

        uri, _ = RTSGMLCCase.write_series!(writer, eastern, values)

        df = DataFrame(Parquet2.Dataset(joinpath(dir, uri)); copycols = true)
        expected = Dates.DateTime.(astimezone.(eastern, tz"UTC"))
        @test df.timestamp == expected
    end
end

@testset "mismatched lengths raise with both lengths named" begin
    mktempdir() do dir
        writer = RTSGMLCCase.SidecarWriter(dir)
        err = try
            RTSGMLCCase.write_series!(writer, _sidecar_timestamps(3), [1.0, 2.0])
            nothing
        catch e
            e
        end
        @test err isa ErrorException
        @test occursin("3", err.msg)
        @test occursin("2", err.msg)
        @test !isdir(joinpath(dir, "timeseries"))
    end
end

@testset "nan payload and signed zero hash as raw bytes" begin
    nan1 = reinterpret(Float64, [reinterpret(UInt64, NaN)])
    nan2 = reinterpret(Float64, [reinterpret(UInt64, NaN) ⊻ UInt64(1)])
    @test RTSGMLCCase.data_hash(collect(nan1)) != RTSGMLCCase.data_hash(collect(nan2))
    @test RTSGMLCCase.data_hash([0.0]) != RTSGMLCCase.data_hash([-0.0])
end
