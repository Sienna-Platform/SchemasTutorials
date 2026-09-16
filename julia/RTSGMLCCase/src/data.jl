using Downloads: Downloads
using SHA: sha256
using Tar: Tar
using CodecZlib: GzipDecompressorStream

# Pinned RTS-GMLC v0.2.2 release — matches the Julia and Python tutorials so both languages
# build from an identical source snapshot.
const SOURCE_URL = "https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz"
const SOURCE_SHA256 = "f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2"

const SOURCE_DATA = "SourceData"
const TIMESERIES_DATA = "timeseries_data_files"

const REQUIRED_SOURCE_TABLES = (
    "bus.csv",
    "branch.csv",
    "gen.csv",
    "dc_branch.csv",
    "reserves.csv",
    "storage.csv",
    "timeseries_pointers.csv",
)

const REPO_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))

"""
    _missing_entries(rts_data) -> Vector{String}

Names of the required tables (under `SourceData/`) and the `timeseries_data_files`
directory absent from an already-extracted `RTS_Data` tree at `rts_data`. Empty
when the tree is complete.
"""
function _missing_entries(rts_data::AbstractString)
    missing_names = String[]
    source_data = joinpath(rts_data, SOURCE_DATA)
    for name in REQUIRED_SOURCE_TABLES
        if !isfile(joinpath(source_data, name))
            push!(missing_names, joinpath(SOURCE_DATA, name))
        end
    end
    if !isdir(joinpath(rts_data, TIMESERIES_DATA))
        push!(missing_names, TIMESERIES_DATA)
    end
    return missing_names
end

"""
    rts_source_dir(repo_root=REPO_ROOT) -> String

Return the path to the cached `RTS_Data` directory, downloading and extracting
the pinned RTS-GMLC v0.2.2 tarball into `<repo_root>/data/RTS-GMLC/` on first use.

An existing cache is verified table-by-table rather than trusting one marker
file — a partial or corrupted tree raises, naming exactly what is missing,
rather than being silently re-downloaded or returned incomplete. This cache is
shared with the Python tutorial: whichever tutorial runs first populates it.
"""
function rts_source_dir(repo_root::AbstractString = REPO_ROOT)
    root = joinpath(repo_root, "data", "RTS-GMLC")
    if isdir(root)
        missing_names = _missing_entries(joinpath(root, "RTS_Data"))
        if !isempty(missing_names)
            error(
                "$root exists but is missing required files/directories: " *
                join(missing_names, ", ") *
                ". Delete $root and re-run to redownload — it will not be silently redownloaded over.",
            )
        end
        return joinpath(root, "RTS_Data")
    end

    parent = dirname(root)
    mkpath(parent)
    for entry in readdir(parent; join = true)
        if startswith(basename(entry), ".RTS-GMLC-staging-") && isdir(entry)
            rm(entry; recursive = true, force = true)
        end
    end

    # Extract into a staging directory and move it into place only on full success, so a
    # crash mid-download or mid-extraction can never leave `root` half-populated.
    staging = mktempdir(parent; prefix = ".RTS-GMLC-staging-")
    try
        tar_path = joinpath(staging, "rts.tar.gz")
        Downloads.download(SOURCE_URL, tar_path)
        digest = bytes2hex(open(sha256, tar_path))
        if digest != SOURCE_SHA256
            rm(tar_path)
            error("checksum mismatch for $SOURCE_URL: $digest")
        end

        # Pass an explicit destination: with none, `Tar.extract` (via ArgTools'
        # `arg_mkdir(f, ::Nothing)`) creates its own independent temp directory in the
        # system temp area instead of under `staging`, so a crash between extraction and
        # cleanup would leak a directory the staging sweep above can never find. Naming the
        # destination keeps every artifact this function creates inside `staging`.
        extracted = joinpath(staging, "extracted")
        open(tar_path) do io
            Tar.extract(GzipDecompressorStream(io), extracted)
        end
        rm(tar_path)

        # The tarball's own top directory (e.g. "RTS-GMLC-0.2.2") wraps everything one level
        # deeper than we want; lift its contents into the staging root.
        inner = only(readdir(extracted; join = true))
        for child in readdir(inner; join = true)
            mv(child, joinpath(staging, basename(child)))
        end
        rm(extracted; recursive = true)

        missing_names = _missing_entries(joinpath(staging, "RTS_Data"))
        if !isempty(missing_names)
            error(
                "extraction of $SOURCE_URL completed but is missing required files/directories: " *
                join(missing_names, ", "),
            )
        end
        mv(staging, root)
    finally
        if isdir(staging)
            rm(staging; recursive = true, force = true)
        end
    end
    return joinpath(root, "RTS_Data")
end
