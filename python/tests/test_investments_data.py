import pytest

from rts_gmlc_case.investments import data


def test_source_dir_exists_and_has_all_required_files():
    src = data.investments_source_dir()
    for name in data.REQUIRED_FILES:
        assert (src / name).is_file(), name


def test_source_dir_matches_exactly_the_16_required_files():
    src = data.investments_source_dir()
    on_disk = {
        str(path.relative_to(src)) for path in src.rglob("*") if path.is_file()
    }
    assert on_disk == set(data.REQUIRED_FILES)


def test_missing_directory_raises_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "REPO_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="does not exist"):
        data.investments_source_dir()


def test_partial_directory_raises_with_missing_names(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "REPO_ROOT", tmp_path)
    root = tmp_path / "data" / "RTS-investments"
    (root / "capacitydata").mkdir(parents=True)
    (root / "hierarchy_rts.csv").write_text("")
    (root / "scalars.csv").write_text("")

    with pytest.raises(RuntimeError) as exc_info:
        data.investments_source_dir()

    message = str(exc_info.value)
    present = {"hierarchy_rts.csv", "scalars.csv"}
    for name in data.REQUIRED_FILES:
        if name in present:
            continue
        assert name in message
