import re

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rts_gmlc_case import sidecar
from rts_gmlc_case.sidecar import SidecarWriter, data_hash

HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def test_pinned_cross_language_hash():
    # Controller-verified literal (CAMPAIGN-FACTS.md canonical hash pin) —
    # the Julia sidecar implementation is pinned to the same value.
    assert data_hash(np.array([1.0, 2.0, 3.0])) == (
        "a68de4b5e96a60c8ceb3c7b7ef93461725bdbbff3516b136585a743b5c0ec664"
    )


def test_hash_is_64_lowercase_hex_chars():
    assert HASH_RE.match(data_hash(np.array([1.0, 2.0, 3.0])))


def test_integer_input_hashes_as_float64():
    # An all-integer array must be forced to float64 before hashing, or its
    # bytes differ from the float64 encoding of the same logical values.
    int_hash = data_hash(np.array([1, 2, 3]))
    float_hash = data_hash(np.array([1.0, 2.0, 3.0]))
    assert int_hash == float_hash


def _timestamps(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")


def test_dedup_same_values_twice_yields_one_file_same_uri(tmp_path):
    writer = SidecarWriter(tmp_path)
    values = np.array([1.0, 2.0, 3.0])
    timestamps = _timestamps(3)

    uri1, hash1 = writer.write(timestamps, values)
    uri2, hash2 = writer.write(timestamps, values)

    assert uri1 == uri2
    assert hash1 == hash2
    assert HASH_RE.match(hash1)

    files = list((tmp_path / "timeseries").glob("*.parquet"))
    assert len(files) == 1
    assert uri1 == f"timeseries/ts_{hash1[:16]}.parquet"


def test_distinct_values_yield_distinct_files(tmp_path):
    writer = SidecarWriter(tmp_path)
    timestamps = _timestamps(3)

    uri1, hash1 = writer.write(timestamps, np.array([1.0, 2.0, 3.0]))
    uri2, hash2 = writer.write(timestamps, np.array([4.0, 5.0, 6.0]))

    assert uri1 != uri2
    assert hash1 != hash2

    files = list((tmp_path / "timeseries").glob("*.parquet"))
    assert len(files) == 2


def test_round_trip_values_and_timestamp_type(tmp_path):
    writer = SidecarWriter(tmp_path)
    values = np.array([1.5, 2.5, 3.5])
    timestamps = _timestamps(3)

    uri, _ = writer.write(timestamps, values)

    table = pq.read_table(tmp_path / uri)
    assert table.schema.field("timestamp").type == pa.timestamp("ms", tz="UTC")
    assert table.schema.field("value").type == pa.float64()

    read_values = table.column("value").to_numpy()
    assert np.array_equal(read_values, values.astype("<f8"))

    read_ts = table.column("timestamp").to_pylist()
    expected_ts = list(timestamps.to_pydatetime())
    assert [t.replace(tzinfo=None) for t in read_ts] == [
        t.replace(tzinfo=None) for t in expected_ts
    ]


def test_write_returns_uri_relative_to_case_dir(tmp_path):
    writer = SidecarWriter(tmp_path)
    uri, data_hash_value = writer.write(_timestamps(3), np.array([9.0, 8.0, 7.0]))
    assert uri.startswith("timeseries/ts_")
    assert uri.endswith(".parquet")
    assert data_hash_value[:16] in uri


def test_corrupt_file_at_hash_path_is_replaced(tmp_path):
    # A prior interrupted run (or any other corruption) can leave garbage
    # bytes at the content-addressed path. `write` must not treat mere
    # existence as proof of a valid file — it must overwrite atomically so
    # the path is either absent or a complete, readable parquet file.
    writer = SidecarWriter(tmp_path)
    values = np.array([1.0, 2.0, 3.0])
    timestamps = _timestamps(3)

    digest = data_hash(values)
    corrupt_path = tmp_path / "timeseries" / f"ts_{digest[:16]}.parquet"
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_bytes(b"not a parquet file")

    uri, returned_hash = writer.write(timestamps, values)

    assert returned_hash == digest
    table = pq.read_table(tmp_path / uri)
    assert np.array_equal(table.column("value").to_numpy(), values.astype("<f8"))


def test_tz_naive_timestamps_raise(tmp_path):
    writer = SidecarWriter(tmp_path)
    naive = pd.date_range("2020-01-01", periods=3, freq="h")
    with pytest.raises(ValueError, match="tz"):
        writer.write(naive, np.array([1.0, 2.0, 3.0]))


def test_tz_aware_non_utc_converts_to_correct_instant(tmp_path):
    writer = SidecarWriter(tmp_path)
    eastern = pd.date_range("2020-01-01", periods=3, freq="h", tz="US/Eastern")
    values = np.array([1.0, 2.0, 3.0])

    uri, _ = writer.write(eastern, values)

    table = pq.read_table(tmp_path / uri)
    read_ts = table.column("timestamp").to_pylist()
    expected_utc = list(eastern.tz_convert("UTC").to_pydatetime())
    assert [t.replace(tzinfo=None) for t in read_ts] == [
        t.replace(tzinfo=None) for t in expected_utc
    ]


def test_mismatched_lengths_raise_with_both_lengths_named(tmp_path):
    writer = SidecarWriter(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        writer.write(_timestamps(3), np.array([1.0, 2.0]))
    message = str(exc_info.value)
    assert "3" in message
    assert "2" in message
    assert not (tmp_path / "timeseries").exists()


def test_nan_payload_and_signed_zero_hash_as_raw_bytes():
    # Deliberate: this store hashes raw IEEE-754 bytes, not canonicalized
    # values. Two NaNs with different mantissa payloads, and +0.0/-0.0
    # (which compare equal), must hash differently.
    nan1 = np.array([np.nan], dtype="<f8")
    nan2 = nan1.copy()
    nan2.view(np.uint64)[0] ^= 1  # flip a low mantissa bit -> different NaN payload
    assert data_hash(nan1) != data_hash(nan2)

    assert data_hash(np.array([0.0])) != data_hash(np.array([-0.0]))


def test_write_failure_cleans_up_temp_file_and_propagates(tmp_path, monkeypatch):
    # Inject at os.replace, not pq.write_table: by the time os.replace runs,
    # the temp file has genuinely been written to disk, so this test can
    # actually observe whether the cleanup handler removes it. Injecting at
    # pq.write_table instead is vacuous -- the mock raises before any temp
    # file exists, so there is nothing to clean up and the test would pass
    # even with no cleanup code at all.
    def _boom(*args, **kwargs):
        raise RuntimeError("injected os.replace failure")

    monkeypatch.setattr(sidecar.os, "replace", _boom)

    writer = SidecarWriter(tmp_path)
    with pytest.raises(RuntimeError, match="injected os.replace failure"):
        writer.write(_timestamps(3), np.array([1.0, 2.0, 3.0]))

    leftovers = list((tmp_path / "timeseries").glob("*.tmp"))
    assert leftovers == []
