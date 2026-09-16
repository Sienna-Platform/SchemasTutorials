using SHA: sha256, bytes2hex
using TimeZones: ZonedDateTime, astimezone, @tz_str
using Dates: DateTime
using Parquet2: Parquet2
using UUIDs: uuid4

# Parquet time-series sidecar, identical in contract to the Python `SidecarWriter`:
#
# - Sidecar folder `timeseries/` beside `system.json`.
# - One parquet file per **distinct** series, named `ts_<first 16 hex of data_hash>.parquet`.
# - Two columns: `timestamp` (UTC, millisecond precision), `value` as float64.
# - `data_hash` is a SHA-256 hex digest over the value vector's float64 little-endian bytes --
#   `<f8` rather than the platform-native byte order, so the digest is reproducible across
#   machines and across the Julia/Python language boundary.
# - Content-dedup: writing the same values twice yields one file and the same `uri`.
#
# The hash covers only `values`, not `timestamps`. NaN payload bits and signed zero are hashed
# as-is (raw IEEE-754 bytes), not canonicalized.
const TIMESERIES_DIR = "timeseries"

"""
    data_hash(values::Vector{Float64}) -> String

SHA-256 hex digest over `values` as float64 little-endian bytes. Forcing little-endian (rather
than the platform-native byte order) makes the digest reproducible across machines and
languages -- Julia's `Float64` is already little-endian on essentially every real target, but
`htol` makes that explicit rather than assumed.
"""
function data_hash(values::Vector{Float64})
    little_endian = htol.(values)
    bytes = reinterpret(UInt8, little_endian)
    return bytes2hex(sha256(collect(bytes)))
end

"""
    SidecarWriter

Writes value/timestamp pairs as content-addressed parquet files under `<case_dir>/timeseries/`.
"""
struct SidecarWriter
    case_dir::String
    timeseries_dir::String
end

function SidecarWriter(case_dir::AbstractString)
    dir = String(case_dir)
    return SidecarWriter(dir, joinpath(dir, TIMESERIES_DIR))
end

"""
    write_series!(writer::SidecarWriter, timestamps::Vector{ZonedDateTime}, values::Vector{Float64}) ->
        (uri::String, data_hash::String)

Write `values` (with matching `timestamps`) to a parquet file, returning `(uri, data_hash)`.
`uri` is relative to the case document. The write is atomic and unconditional: content that
hashes to the same path is (re)written every call rather than trusting a prior file's mere
existence, so a corrupt or partial file at that path is always replaced with a valid one.

`timestamps` is always timezone-aware (Julia's `ZonedDateTime` cannot be tz-naive, unlike
Python's `DatetimeIndex`, so there is no naive-input case to reject); any zone other than UTC
is converted. Raises if `timestamps` and `values` have different lengths.
"""
function write_series!(
    writer::SidecarWriter,
    timestamps::Vector{ZonedDateTime},
    values::Vector{Float64},
)
    length(timestamps) == length(values) || error(
        "timestamps and values have different lengths: " *
        "$(length(timestamps)) != $(length(values))",
    )

    digest = data_hash(values)
    stem = digest[1:16]
    filename = "ts_$stem.parquet"
    uri = "$TIMESERIES_DIR/$filename"
    path = joinpath(writer.timeseries_dir, filename)

    # Always (re)write, atomically, rather than trusting `isfile(path)` as a proxy for "a valid
    # file is already there": a prior interrupted run or any other corruption can leave garbage
    # bytes at this content-addressed path, and mere existence cannot distinguish that from a
    # genuine file. Writing to a uniquely-named temp file in the same directory and then `mv`
    # (force = true) into position is atomic on a given filesystem, so `path` ends up either
    # absent or a complete, valid file -- never half-written or stale garbage.
    mkpath(writer.timeseries_dir)
    utc_timestamps = DateTime.(astimezone.(timestamps, tz"UTC"))
    table = (timestamp = utc_timestamps, value = values)

    tmp_path = joinpath(
        writer.timeseries_dir,
        ".$(filename).$(getpid()).$(uuid4()).tmp",
    )
    try
        Parquet2.writefile(tmp_path, table)
        mv(tmp_path, path; force = true)
    catch
        rm(tmp_path; force = true)
        rethrow()
    end

    return uri, digest
end
