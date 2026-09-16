"""Parquet time-series sidecar (see CAMPAIGN-FACTS.md's cross-language hash
pin and R32 for how ``TimeSeriesAssociation`` records consume this).

Contract, identical on the Julia side:

- Sidecar folder ``timeseries/`` beside ``system.json``.
- One parquet file per **distinct** series, named
  ``ts_<first 16 hex of data_hash>.parquet``.
- Two columns: ``timestamp`` as ``pa.timestamp("ms", tz="UTC")``, ``value``
  as float64.
- ``data_hash`` is a SHA-256 hex digest over the value vector's float64
  little-endian bytes — ``<f8`` rather than the platform-native ``f8``,
  because native byte order depends on the machine (big-endian on some
  architectures) while ``<f8`` is fixed, making the hash portable across
  machines and across the Python/Julia language boundary.
- Content-dedup: writing the same values twice yields one file and the same
  ``uri``.

**The hash covers only ``values``, not ``timestamps``.** The ``timestamp``
column's dtype and UTC-ms contract are enforced by this writer (tz-naive
input is rejected; tz-aware non-UTC input is converted), but that contract
is not part of ``data_hash`` and is not otherwise hash-verified. Do not
assume the hash pins the whole file — it pins the value vector.

**NaN payload bits and signed zero are hashed as-is, not canonicalized.**
This is deliberate: ``data_hash`` hashes the raw IEEE-754 bytes of
``values``, so two NaNs that differ only in mantissa payload hash
differently, and ``0.0`` / ``-0.0`` — which compare equal — hash
differently too. A byte-identical hash is the point of a
cross-language content address; silently normalizing NaN payloads or
signed zero would hide a real bit-level difference between two producers.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TIMESERIES_DIR = "timeseries"


def data_hash(values: np.ndarray) -> str:
    """SHA-256 hex digest over ``values`` as float64 little-endian bytes.

    Forcing ``<f8`` (not the platform-native dtype) makes the digest
    reproducible across machines and languages: an all-integer input array
    is cast to float64 first, matching what Julia's ``Float64`` values hash
    to. NaN payload bits and the sign of zero are hashed as-is (see module
    docstring) — this is a raw-bytes digest, not a value-equality one.
    """
    return hashlib.sha256(np.ascontiguousarray(values, dtype="<f8").tobytes()).hexdigest()


class SidecarWriter:
    """Writes value/timestamp pairs as content-addressed parquet files
    under ``<case_dir>/timeseries/``.
    """

    def __init__(self, case_dir: Path) -> None:
        self._case_dir = Path(case_dir)
        self._timeseries_dir = self._case_dir / TIMESERIES_DIR

    def write(self, timestamps: pd.DatetimeIndex, values: np.ndarray) -> tuple[str, str]:
        """Write ``values`` (with matching ``timestamps``) to a parquet
        file, returning ``(uri, data_hash)``. ``uri`` is relative to the
        case document. The write is atomic and unconditional: content that
        hashes to the same path is (re)written every call rather than
        trusting a prior file's mere existence, so a corrupt or partial
        file at that path is always replaced with a valid one.

        ``timestamps`` must be timezone-aware (tz-naive input is rejected
        rather than silently assumed to be UTC); non-UTC tz-aware input is
        converted to UTC. Raises ``ValueError`` if ``timestamps`` and
        ``values`` have different lengths.
        """
        if len(timestamps) != len(values):
            raise ValueError(
                f"timestamps and values have different lengths: "
                f"{len(timestamps)} != {len(values)}"
            )
        if timestamps.tz is None:
            raise ValueError(
                "timestamps must be timezone-aware, got a tz-naive "
                "DatetimeIndex — localize it (e.g. to UTC) before calling "
                "write(); a naive index is never silently assumed to be UTC"
            )

        digest = data_hash(values)
        stem = digest[:16]
        filename = f"ts_{stem}.parquet"
        uri = f"{TIMESERIES_DIR}/{filename}"
        path = self._timeseries_dir / filename

        # Always (re)write, atomically, rather than trusting `path.exists()`
        # as a proxy for "a valid file is already there": a prior interrupted
        # run or any other corruption can leave garbage bytes at this
        # content-addressed path, and mere existence cannot distinguish that
        # from a genuine file. Writing to a temp file in the same directory
        # and then os.replace-ing it into position is atomic on a given
        # filesystem, so `path` ends up either absent or a complete, valid
        # file — never a half-written or stale-garbage one. The redundant
        # write when the content already exists and is valid is cheap
        # compared to the correctness this buys.
        self._timeseries_dir.mkdir(parents=True, exist_ok=True)
        table = pa.table(
            {
                "timestamp": pa.array(timestamps, type=pa.timestamp("ms", tz="UTC")),
                "value": pa.array(
                    np.ascontiguousarray(values, dtype="<f8"), type=pa.float64()
                ),
            }
        )
        # A pid-only suffix can collide between two concurrent write() calls
        # in the same process for the same digest; a uuid4 fragment makes
        # each call's temp path unique, so cleanup below can unambiguously
        # remove exactly the file this call created.
        tmp_path = path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            pq.write_table(table, tmp_path)
            os.replace(tmp_path, path)
        except BaseException:
            # os.replace succeeding means tmp_path no longer exists (it was
            # moved to path), so only clean up if the write itself failed
            # partway, or replace failed after a successful write.
            tmp_path.unlink(missing_ok=True)
            raise

        return uri, digest
