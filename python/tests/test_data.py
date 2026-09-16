import pytest

from rts_gmlc_case import data


def test_source_dir_exists_and_has_tables():
    src = data.rts_source_dir()
    for name in data.REQUIRED_SOURCE_TABLES:
        assert (src / data.SOURCE_DATA / name).is_file()
    assert (src / data.TIMESERIES_DATA).is_dir()


def test_partial_cache_raises_with_missing_names(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "REPO_ROOT", tmp_path)
    source_data = tmp_path / "data" / "RTS-GMLC" / "RTS_Data" / data.SOURCE_DATA
    source_data.mkdir(parents=True)
    (source_data / "bus.csv").write_text("")

    with pytest.raises(RuntimeError) as exc_info:
        data.rts_source_dir()

    message = str(exc_info.value)
    for name in ("branch.csv", "gen.csv", "dc_branch.csv", "reserves.csv", "storage.csv", "timeseries_pointers.csv"):
        assert name in message
    assert data.TIMESERIES_DATA in message
