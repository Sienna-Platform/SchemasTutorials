# The pinned, checksum-verified download that `rts_gmlc_case.data` performs
# for the operations dataset is not wired up here: no verified upstream URL
# for the ReEDS-style RTS-investments inputs was available this session. A
# future session can add it the same way `rts_gmlc_case.data.rts_source_dir`
# does, once someone identifies the authoritative source. For now this
# module only validates that the dataset already exists locally.

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

REQUIRED_FILES = (
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


def _missing_entries(rts_data: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (rts_data / name).is_file()]


def investments_source_dir() -> Path:
    """Return ``data/RTS-investments/`` after validating that all 16
    required files are present. Raises ``RuntimeError`` naming the
    directory if it doesn't exist at all (this module never downloads it),
    or naming every missing path if the directory exists but is
    incomplete.
    """
    root = REPO_ROOT / "data" / "RTS-investments"
    if not root.exists():
        raise RuntimeError(
            f"{root} does not exist. Place the RTS-investments dataset "
            "there — this module does not download it."
        )

    missing = _missing_entries(root)
    if missing:
        raise RuntimeError(
            f"{root} exists but is missing required files: {', '.join(missing)}."
        )
    return root
