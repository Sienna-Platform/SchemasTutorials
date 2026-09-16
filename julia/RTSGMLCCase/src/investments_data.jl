# The pinned, checksum-verified download that `rts_source_dir` performs for the operations
# dataset is not wired up here: no verified upstream URL for the ReEDS-style RTS-investments
# inputs was available this session. A future session can add it the same way
# `rts_source_dir` does, once someone identifies the authoritative source. For now this file
# only validates that the dataset already exists locally.

const INVESTMENTS_REPO_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))

const REQUIRED_INVESTMENTS_FILES = (
    "hierarchy_rts.csv",
    "scalars.csv",
    "capacitydata/ReEDS_generator_database_final_RTS-GMLC_updated_nodal.csv",
    "capacitydata/upv_exog_cap_reference_nodal.csv",
    "capacitydata/wind-ons_exog_cap_reference_nodal.csv",
    "financials/reg_cap_cost_mult_nodal_rts.csv",
    "loaddata/RTS_DA_regional_load.csv",
    "storagedata/storage_duration_pshdata.csv",
    "storagedata/storinmaxfrac.csv",
    "supplycurvedata/hyd_add_upg_cap.csv",
    "supplycurvedata/upv_supply_curve-reference_nodal.csv",
    "supplycurvedata/wind-ons_supply_curve-reference_nodal.csv",
    "transmission/transmission_capacity_init_AC_rts_nodal.csv",
    "transmission/transmission_capacity_init_nonAC_nodal.csv",
    "transmission/transmission_distance_cost_500kVac_nodal.csv",
    "transmission/transmission_distance_cost_500kVdc_nodal.csv",
)

"""
    _missing_investments_entries(rts_data) -> Vector{String}

Names of `REQUIRED_INVESTMENTS_FILES` absent from `rts_data`. Empty when the tree is complete.
"""
function _missing_investments_entries(rts_data::AbstractString)
    missing_names = String[]
    for name in REQUIRED_INVESTMENTS_FILES
        if !isfile(joinpath(rts_data, name))
            push!(missing_names, name)
        end
    end
    return missing_names
end

"""
    investments_source_dir(repo_root=INVESTMENTS_REPO_ROOT) -> String

Return `<repo_root>/data/RTS-investments/` after validating that all 16 required files are
present. Errors naming the directory if it doesn't exist at all (this function never downloads
it), or naming every missing path if the directory exists but is incomplete.
"""
function investments_source_dir(repo_root::AbstractString = INVESTMENTS_REPO_ROOT)
    root = joinpath(repo_root, "data", "RTS-investments")
    if !isdir(root)
        error("$root does not exist. Place the RTS-investments dataset there — this function does not download it.")
    end

    missing_names = _missing_investments_entries(root)
    if !isempty(missing_names)
        error("$root exists but is missing required files: " * join(missing_names, ", ") * ".")
    end
    return root
end
