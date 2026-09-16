"""The combined build driver: operations stages onto a ``SystemDocument``,
then every investments stage onto a ``PortfolioDocument``, sharing one id
counter.

A portfolio is its own document — ``Investments/PortfolioDocument.json`` —
not a set of extra buckets inside the system. It is written beside the
system as ``portfolio.json`` and names it in ``base_system_file``, so the
pair can be moved and read together. The shared id counter is what lets a
technology's ``region`` name an ``ACBus`` or ``Area`` id that lives in the
base system.

Stage order is fixed and load-bearing (mirrors ``rts_gmlc_case.build``'s own
docstring warning):

    topology -> branches -> generation -> loads -> reserves -> time series
    -> investment topology -> supply technologies -> storage technologies
    -> transport technologies -> demand requirements -> policy constraints

The operations half is unchanged from ``rts_gmlc_case.build.build_case`` --
same functions, same order. The investments half runs E1 through E5 in
that order on top of it. Both halves share the same ``SidecarWriter``
instance (one ``timeseries/`` directory, one content-addressed store for
the whole combined case) and one id counter, so operations and investments
components share one continuous id space. The
Julia mirror of this driver must reproduce the same order for id-sequence
parity between languages (the cross-language equivalence test depends on
it).
"""

from __future__ import annotations

from pathlib import Path

from rts_gmlc_case import data
from rts_gmlc_case.branches import add_branches
from rts_gmlc_case.build import SYSTEM_FILENAME

PORTFOLIO_FILENAME = "portfolio.json"
from rts_gmlc_case.demand import add_loads, add_reserves
from rts_gmlc_case.document import CaseDocument, PortfolioCase
from rts_gmlc_case.generation import add_generation
from rts_gmlc_case.investments import data as investments_data
from rts_gmlc_case.investments.demand import add_demand_requirements
from rts_gmlc_case.investments.policy import add_policy_constraints
from rts_gmlc_case.investments.storage import add_storage_technologies
from rts_gmlc_case.investments.technologies import add_supply_technologies
from rts_gmlc_case.investments.topology import add_investment_topology
from rts_gmlc_case.investments.transport import add_transport_technologies
from rts_gmlc_case.sidecar import SidecarWriter
from rts_gmlc_case.timeseries import TimeSeriesOwners, attach_time_series
from rts_gmlc_case.topology import add_topology


def build_expansion_case(case_dir: str | Path) -> tuple[CaseDocument, PortfolioCase]:
    """Build the combined operations + investments RTS-GMLC case and write
    it into ``case_dir``.

    Runs every operations stage in ``rts_gmlc_case.build.build_case``'s
    fixed order onto a ``CaseDocument``, then every investments stage
    (E1 -> E2 -> E3 -> E4 -> E5) onto a ``PortfolioCase`` built against it,
    reusing the same ``SidecarWriter`` instance across both halves.
    Validates both, then writes ``case_dir/system.json``,
    ``case_dir/portfolio.json``, and the ``timeseries/`` parquet sidecar.
    Returns the built pair.
    """
    case_dir = Path(case_dir)
    source = data.rts_source_dir() / "SourceData"
    inv_source = investments_data.investments_source_dir()

    doc = CaseDocument()

    # Operations half (unchanged order).
    idx = add_topology(doc, source)
    add_branches(doc, source, idx)
    gen_ids = add_generation(doc, source, idx)
    add_loads(doc, source, idx)
    reserve_ids = add_reserves(doc, source, idx, gen_ids)

    sidecar = SidecarWriter(case_dir)
    owners = TimeSeriesOwners(
        generator_id_by_uid=gen_ids,
        area_id_by_name=idx.area_id_by_name,
        reserve_id_by_product=reserve_ids,
    )
    attach_time_series(doc, source, sidecar, owners)

    # Investments half (E1 -> E2 -> E3 -> E4 -> E5), own document, shared id
    # counter, same sidecar.
    portfolio = PortfolioCase(
        doc,
        # The regional aggregation the portfolio groups by. RTS Areas are the
        # zones every technology's `region` points at -- see
        # `rts_gmlc_case.investments.topology`.
        aggregation="Area",
        base_system_file=SYSTEM_FILENAME,
    )
    inv_idx = add_investment_topology(portfolio, inv_source, idx)
    supply_ids = add_supply_technologies(portfolio, inv_source, idx, inv_idx)
    storage_ids = add_storage_technologies(portfolio, inv_source, inv_idx)
    add_transport_technologies(portfolio, inv_source, inv_idx)
    add_demand_requirements(portfolio, inv_source, sidecar, inv_idx)
    add_policy_constraints(portfolio, supply_ids, storage_ids)

    doc.validate()
    portfolio.validate()

    case_dir.mkdir(parents=True, exist_ok=True)
    doc.write(case_dir / SYSTEM_FILENAME)
    portfolio.write(case_dir / PORTFOLIO_FILENAME)

    return doc, portfolio


def read_expansion_case(case_dir: str | Path) -> tuple[CaseDocument, PortfolioCase]:
    """Read a case previously written by ``build_expansion_case`` back from
    ``case_dir``, as the ``(system, portfolio)`` pair it was written as.

    The system half reuses ``rts_gmlc_case.build.read_case`` -- that function
    is already generic over ``case_dir`` and reuses the same
    ``SYSTEM_FILENAME``, so it is not duplicated here.
    """
    from rts_gmlc_case.build import read_case

    doc = read_case(case_dir)
    portfolio = PortfolioCase.read(Path(case_dir) / PORTFOLIO_FILENAME, doc)
    portfolio.typed_components()
    portfolio.validate()
    return doc, portfolio
