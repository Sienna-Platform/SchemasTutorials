import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

URL = "https://github.com/GridMod/RTS-GMLC/archive/refs/tags/v0.2.2.tar.gz"
SHA256 = "f7a816f2390b96d44fa931c2790e2ec5ef81d0deb503c4c719b25ec1b585e2c2"
REPO_ROOT = Path(__file__).resolve().parents[3]

SOURCE_DATA = "SourceData"
TIMESERIES_DATA = "timeseries_data_files"

REQUIRED_SOURCE_TABLES = (
    "bus.csv",
    "branch.csv",
    "gen.csv",
    "dc_branch.csv",
    "reserves.csv",
    "storage.csv",
    "timeseries_pointers.csv",
)


def _missing_entries(rts_data: Path) -> list[str]:
    source_data = rts_data / SOURCE_DATA
    missing = [
        f"{SOURCE_DATA}/{name}"
        for name in REQUIRED_SOURCE_TABLES
        if not (source_data / name).is_file()
    ]
    if not (rts_data / TIMESERIES_DATA).is_dir():
        missing.append(TIMESERIES_DATA)
    return missing


def rts_source_dir() -> Path:
    root = REPO_ROOT / "data" / "RTS-GMLC"
    if root.exists():
        missing = _missing_entries(root / "RTS_Data")
        if missing:
            raise RuntimeError(
                f"{root} exists but is missing required files/directories: "
                f"{', '.join(missing)}. Delete {root} and re-run to redownload — "
                "it will not be silently redownloaded over."
            )
        return root / "RTS_Data"

    root.parent.mkdir(parents=True, exist_ok=True)
    for stale in root.parent.glob(".RTS-GMLC-staging-*"):
        shutil.rmtree(stale, ignore_errors=True)

    staging = Path(tempfile.mkdtemp(prefix=".RTS-GMLC-staging-", dir=root.parent))
    try:
        tar_path = staging / "rts.tar.gz"
        urllib.request.urlretrieve(URL, tar_path)
        digest = hashlib.sha256(tar_path.read_bytes()).hexdigest()
        if digest != SHA256:
            tar_path.unlink()
            raise RuntimeError(f"checksum mismatch for {URL}: {digest}")
        with tarfile.open(tar_path) as tf:
            tf.extractall(staging, filter="data")
        tar_path.unlink()

        inner = next(staging.glob("RTS-GMLC-*"))
        for child in inner.iterdir():
            child.rename(staging / child.name)
        inner.rmdir()

        missing = _missing_entries(staging / "RTS_Data")
        if missing:
            raise RuntimeError(
                f"extraction of {URL} completed but is missing required "
                f"files/directories: {', '.join(missing)}"
            )
        staging.rename(root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return root / "RTS_Data"
