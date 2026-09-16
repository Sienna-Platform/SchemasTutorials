# --- read_profile: Layout A (Period column, object columns) ---------------

@testset "read_profile layout a period resets daily" begin
    mktempdir() do dir
        path = joinpath(dir, "layout_a.csv")
        write(
            path,
            "Year,Month,Day,Period,OBJ_A,OBJ_B\n" *
            "2020,1,1,1,10.0,100.0\n" *
            "2020,1,1,2,11.0,101.0\n" *
            "2020,1,1,3,12.0,102.0\n" *
            "2020,1,2,1,13.0,103.0\n" *
            "2020,1,2,2,14.0,104.0\n" *
            "2020,1,2,3,15.0,105.0\n",
        )

        timestamps, values = RTSGMLCCase.read_profile(path, "OBJ_A", Dates.Hour(1))
        @test values == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        expected = [
            ZonedDateTime(2020, 1, 1, 0, tz"UTC"),
            ZonedDateTime(2020, 1, 1, 1, tz"UTC"),
            ZonedDateTime(2020, 1, 1, 2, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 0, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 1, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 2, tz"UTC"),
        ]
        @test timestamps == expected

        _, values_b = RTSGMLCCase.read_profile(path, "OBJ_B", Dates.Hour(1))
        @test values_b == [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    end
end

@testset "read_profile layout a requires a column" begin
    mktempdir() do dir
        path = joinpath(dir, "layout_a_single.csv")
        write(path, "Year,Month,Day,Period,OBJ_A\n2020,1,1,1,10.0\n")
        @test_throws ErrorException RTSGMLCCase.read_profile(path, nothing, Dates.Hour(1))
    end
end

@testset "read_profile layout a unknown column raises" begin
    mktempdir() do dir
        path = joinpath(dir, "layout_a_single2.csv")
        write(path, "Year,Month,Day,Period,OBJ_A\n2020,1,1,1,10.0\n")
        @test_throws ErrorException RTSGMLCCase.read_profile(path, "NOT_A_COLUMN", Dates.Hour(1))
    end
end

# --- read_profile: Layout B (no Period column, periods as columns) --------

@testset "read_profile layout b flattens row major" begin
    mktempdir() do dir
        path = joinpath(dir, "layout_b.csv")
        write(
            path,
            "Year,Month,Day,1,2,3\n" * "2020,1,1,10.0,11.0,12.0\n" * "2020,1,2,13.0,14.0,15.0\n",
        )

        timestamps, values = RTSGMLCCase.read_profile(path, nothing, Dates.Hour(1))
        @test values == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        expected = [
            ZonedDateTime(2020, 1, 1, 0, tz"UTC"),
            ZonedDateTime(2020, 1, 1, 1, tz"UTC"),
            ZonedDateTime(2020, 1, 1, 2, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 0, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 1, tz"UTC"),
            ZonedDateTime(2020, 1, 2, 2, tz"UTC"),
        ]
        @test timestamps == expected
    end
end

@testset "read_profile layout b ignores column argument" begin
    mktempdir() do dir
        path = joinpath(dir, "layout_b_ignore.csv")
        write(path, "Year,Month,Day,1,2\n2020,1,1,1.0,2.0\n")
        _, values = RTSGMLCCase.read_profile(path, "does-not-matter", Dates.Minute(5))
        @test values == [1.0, 2.0]
    end
end

# --- resolve_case_insensitive_path: the HYDRO/Hydro fix --------------------
#
# Deliberately does NOT use the real RTS data directory: on macOS's case-insensitive
# filesystem a broken resolver would still "pass" against real data, hiding exactly the
# Linux-breaking bug this exists to catch. These build a synthetic tree with a known case
# mismatch instead.

@testset "resolve_case_insensitive_path finds mismatched directory" begin
    mktempdir() do dir
        real_dir = joinpath(dir, "timeseries_data_files", "Hydro")
        mkpath(real_dir)
        write(joinpath(real_dir, "DAY_AHEAD_hydro.csv"), "Year,Month,Day,Period,x\n2020,1,1,1,1.0\n")

        source = joinpath(dir, "SourceData")
        mkpath(source)

        resolved = RTSGMLCCase.resolve_case_insensitive_path(
            source,
            "../timeseries_data_files/HYDRO/DAY_AHEAD_hydro.csv",
        )
        @test resolved == joinpath(real_dir, "DAY_AHEAD_hydro.csv")
        @test isfile(resolved)
    end
end

@testset "resolve_case_insensitive_path finds mismatched filename" begin
    mktempdir() do dir
        real_dir = joinpath(dir, "timeseries_data_files", "Load")
        mkpath(real_dir)
        write(joinpath(real_dir, "REAL_TIME_regional_Load.csv"), "Year,Month,Day,1\n2020,1,1,1.0\n")

        source = joinpath(dir, "SourceData")
        mkpath(source)

        resolved = RTSGMLCCase.resolve_case_insensitive_path(
            source,
            "../timeseries_data_files/Load/REAL_TIME_regional_load.csv",
        )
        @test resolved == joinpath(real_dir, "REAL_TIME_regional_Load.csv")
        @test isfile(resolved)
    end
end

@testset "resolve_case_insensitive_path raises naming path when no match" begin
    mktempdir() do dir
        real_dir = joinpath(dir, "timeseries_data_files", "WIND")
        mkpath(real_dir)

        source = joinpath(dir, "SourceData")
        mkpath(source)

        referenced = "../timeseries_data_files/SOLAR/DAY_AHEAD_solar.csv"
        err = try
            RTSGMLCCase.resolve_case_insensitive_path(source, referenced)
            nothing
        catch e
            e
        end
        @test err isa ErrorException
        @test occursin("SOLAR", err.msg)
    end
end

# --- attach_time_series!: full build on the real RTS-GMLC source data -----

function _timeseries_built_case(dir)
    src = joinpath(RTSGMLCCase.rts_source_dir(), RTSGMLCCase.SOURCE_DATA)
    doc = RTSGMLCCase.new_document()
    idx = RTSGMLCCase.add_topology!(doc, src)
    gen_ids = RTSGMLCCase.add_generation!(doc, src, idx)
    RTSGMLCCase.add_loads!(doc, src, idx)
    reserve_ids = RTSGMLCCase.add_reserves!(doc, src, idx, gen_ids)
    sidecar = RTSGMLCCase.SidecarWriter(dir)
    owners = RTSGMLCCase.TimeSeriesOwners(gen_ids, idx.area_id_by_name, reserve_ids)
    return doc, src, sidecar, owners
end

@testset "attach_time_series counts and resolutions" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        assocs = doc.time_series_associations
        @test length(assocs) == 282

        resolutions = Set(a.value.resolution for a in assocs)
        @test resolutions == Set(["PT1H", "PT5M"])
        @test PowerOpenAPIModels.get_time_series_storage_file(doc) == "timeseries"
    end
end

@testset "attach_time_series uris exist lengths match and dedup holds" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        assocs = [a.value for a in doc.time_series_associations]
        seen_paths = Set{String}()
        for sts in assocs
            path = joinpath(dir, sts.uri)
            @test isfile(path)
            push!(seen_paths, path)
            df = DataFrame(Parquet2.Dataset(path); copycols = true)
            @test nrow(df) == sts.length
            @test sts.array_shape[1] == sts.length
        end

        on_disk = Set(
            joinpath(dir, "timeseries", f) for
            f in readdir(joinpath(dir, "timeseries")) if endswith(f, ".parquet")
        )
        @test on_disk == seen_paths

        # 102 PMin series are byte-identical to their PMax partners, so the sidecar collapses
        # substantially fewer distinct files than the 282 associations.
        @test length(on_disk) < 282
        @test length(on_disk) <= 200
    end
end

@testset "pmax pmin dedup for 122_hydro_1" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        generator_id = owners.generator_id_by_uid["122_HYDRO_1"]
        by_name = Dict{String, Any}()
        for assoc in doc.time_series_associations
            sts = assoc.value
            if sts.owner_id == generator_id && sts.resolution == "PT1H"
                by_name[sts.name] = sts
            end
        end

        pmax = by_name["max_active_power"]
        pmin = by_name["min_active_power"]
        @test pmax.uri == pmin.uri
        @test pmax.data_hash == pmin.data_hash
    end
end

@testset "natural_inflow resolves through storage.csv to 212_csp_1" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        generator_id = owners.generator_id_by_uid["212_CSP_1"]
        inflow = [
            a.value for a in doc.time_series_associations if
            a.value.owner_id == generator_id && a.value.name == "inflow"
        ]
        @test length(inflow) == 2  # DAY_AHEAD + REAL_TIME
        for series in inflow
            @test series.owner_type == "RenewableDispatch"
            @test series.quantity_kind == "power"
        end
    end
end

@testset "owner_category counts generator reserve area" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        generator_ids = Set(values(owners.generator_id_by_uid))
        reserve_ids = Set(values(owners.reserve_id_by_product))
        area_ids = Set(values(owners.area_id_by_name))

        counts = Dict("Generator" => 0, "Reserve" => 0, "Area" => 0)
        for assoc in doc.time_series_associations
            sts = assoc.value
            @test sts.owner_category == PowerOpenAPIModels.OwnerCategory("Component")
            @test sts.element_type == "f64"
            @test sts.time_reference == "zoneless"
            @test sts.unit_system == PowerOpenAPIModels.UnitSystem("NATURAL_UNITS")
            if sts.owner_id in generator_ids && sts.owner_type != "Area"
                counts["Generator"] += 1
            elseif sts.owner_id in reserve_ids && sts.owner_type == "OnlineReserve"
                counts["Reserve"] += 1
            elseif sts.owner_id in area_ids && sts.owner_type == "Area"
                counts["Area"] += 1
            end
        end

        @test counts == Dict("Generator" => 264, "Reserve" => 12, "Area" => 6)
    end
end

@testset "scaling factor applied to values" begin
    mktempdir() do dir
        doc, src, sidecar, owners = _timeseries_built_case(dir)
        RTSGMLCCase.attach_time_series!(doc, src, sidecar, owners)

        pointers = CSV.read(joinpath(src, "timeseries_pointers.csv"), DataFrame)
        row = only(
            filter(
                r ->
                    r["Category"] == "Generator" &&
                        r["Object"] == "122_HYDRO_1" &&
                        r["Parameter"] == "PMax MW" &&
                        r["Simulation"] == "DAY_AHEAD",
                eachrow(pointers),
            ),
        )

        raw = CSV.read(
            RTSGMLCCase.resolve_case_insensitive_path(src, String(row["Data File"])),
            DataFrame,
        )
        expected_first = Float64(raw[1, "122_HYDRO_1"]) * Float64(row["Scaling Factor"])

        generator_id = owners.generator_id_by_uid["122_HYDRO_1"]
        sts = first(
            a.value for a in doc.time_series_associations if
            a.value.owner_id == generator_id &&
            a.value.name == "max_active_power" &&
            a.value.resolution == "PT1H"
        )
        df = DataFrame(Parquet2.Dataset(joinpath(dir, sts.uri)); copycols = true)
        @test df.value[1] ≈ expected_first
    end
end
