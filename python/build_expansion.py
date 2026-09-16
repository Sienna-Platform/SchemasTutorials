#!/usr/bin/env python3
"""CLI: build the full RTS-GMLC capacity-expansion case (operations +
investments) into the given output directory.

Usage:

    uv run python build_expansion.py <output-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from rts_gmlc_case.investments.build import build_expansion_case


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <output-dir>", file=sys.stderr)
        return 2

    case_dir = Path(argv[1])
    doc = build_expansion_case(case_dir)

    counts = {
        type_name: len(items) for type_name, items in sorted(doc.document.components.items())
    }
    print(f"wrote case to {case_dir}")
    print("component counts:")
    for type_name, count in counts.items():
        print(f"  {type_name}: {count}")
    print(f"service_associations: {len(doc.document.service_associations)}")
    print(f"time_series_associations: {len(doc.document.time_series_associations)}")

    parquet_files = list((case_dir / "timeseries").glob("*.parquet"))
    print(f"parquet files: {len(parquet_files)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
