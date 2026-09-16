const SYSTEM_FILENAME = "system.json"

"""
    build_case(case_dir::AbstractString) -> PowerOpenAPIModels.SystemDocument

Build the full RTS-GMLC case from the downloaded source data and write it into `case_dir`.

Runs every stage in the fixed order topology -> branches -> generation -> loads -> reserves ->
time series -- matching the Python tutorial's `build_case` stage order and argument-threading
exactly, so both languages mint an identical id sequence for a given component. Validates the
result, then writes `case_dir/system.json` plus the `timeseries/` parquet sidecar. Returns the
built document.
"""
function build_case(case_dir::AbstractString)
    source = joinpath(rts_source_dir(), SOURCE_DATA)

    doc = new_document()

    idx = add_topology!(doc, source)
    add_branches!(doc, source, idx)
    gen_ids = add_generation!(doc, source, idx)
    add_loads!(doc, source, idx)
    reserve_ids = add_reserves!(doc, source, idx, gen_ids)

    sidecar = SidecarWriter(case_dir)
    owners = TimeSeriesOwners(gen_ids, idx.area_id_by_name, reserve_ids)
    attach_time_series!(doc, source, sidecar, owners)

    PD.validate_document(doc)

    mkpath(case_dir)
    PD.write_document(doc, joinpath(case_dir, SYSTEM_FILENAME); pretty = true, force = true)

    return doc
end

"""
    read_case(case_dir::AbstractString) -> PowerOpenAPIModels.SystemDocument

Read a case previously written by [`build_case`](@ref) back from `case_dir`.
"""
function read_case(case_dir::AbstractString)
    doc = PD.read_document(joinpath(case_dir, SYSTEM_FILENAME))
    PD.validate_document(doc)
    return doc
end
