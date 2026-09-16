using CSV: CSV
using DataFrames: DataFrame, groupby, combine, nrow

# Investments transport-technology stage (E3/JE3): one `NodalACTransportTechnology` per unique
# existing AC corridor and one `NodalHVDCTransportTechnology` for the system's single existing
# HVDC link.
#
# AC data: `transmission/transmission_capacity_init_AC_rts_nodal.csv` (120 rows: `interface`,
# `From_Bus`, `To_Bus`, `MW_f0`, `MW_r0` -- bus ids in `bXXX` form, e.g. `b101`; the leading `b`
# is stripped to join against `InvestmentTopologyIndex.node_id_by_bus_number`) and
# `transmission/transmission_distance_cost_500kVac_nodal.csv` (108 rows: `r`, `rr`,
# `length_miles`, `USD2004perMW`, same `bXXX` join key on `r`/`rr` matching `From_Bus`/`To_Bus`).
#
# **Duplicate-pair resolution.** The capacity file has 120 rows but only 108 distinct
# `(From_Bus, To_Bus)` pairs -- 12 pairs each appear as two *exactly identical* rows (same
# `MW_f0`/`MW_r0`), with no circuit-id column to disambiguate them (unlike operations
# `branch.csv`'s `Circuit`). This module builds **one `NodalACTransportTechnology` per unique
# pair (108 total)**, summing `MW_f0` across duplicate rows for that pair -- read as combined
# parallel-circuit capacity on one investable corridor. Every capacity-file row has
# `MW_f0 == MW_r0` (asserted below), so only `MW_f0` is used. The cost file's 108 rows are
# exactly the capacity file's 108 unique pairs, one row each -- no join gaps either way.
#
# HVDC data: `transmission/transmission_capacity_init_nonAC_nodal.csv` (1 row:
# `b113,b316,LCC,100`) and `transmission/transmission_distance_cost_500kVdc_nodal.csv` (1
# matching row, 70 miles, `USD2004perMW` 644267.96). One `NodalHVDCTransportTechnology` component.
#
# `capital_costs` on both technologies is a genuinely dataset-sourced flat linear `ValueCurve`
# ([`flat_linear_value_curve`](@ref)) built from `USD2004perMW` -- 2004 USD, **no inflation
# adjustment applied** (a real limitation of this dataset, not silently corrected here). Unlike
# the illustrative supply/storage capital costs, this figure is not routed through the
# "illustrative" framing.
#
# `financial_data.capital_recovery_period` is genuinely sourced too: 40 years, from
# `scalars.csv`'s `trans_crp` row -- see [`transport_financial_data`](@ref) for the exact
# citation. That helper's other 5 `TechnologyFinancialData` fields have no transmission-specific
# source in this dataset and are illustrative.
#
# `power_systems_type` follows the same R39 convention E2/JE2 established (the exact PSY type
# name the *operations* campaign would build this class's devices as, per `branches.jl`):
# `"Line"` for AC corridors, `"TwoTerminalGenericHVDCLine"` for the HVDC link.
#
# `resistance`/`reactance`/`voltage`/`unit_size` on `NodalACTransportTechnology`, and `line_loss`
# on `NodalHVDCTransportTechnology`, have no backing dataset field at this stage and are left at
# their schema defaults (`0.0` / `nothing`) rather than invented.

const AC_CAPACITY_FILE = joinpath("transmission", "transmission_capacity_init_AC_rts_nodal.csv")
const AC_COST_FILE = joinpath("transmission", "transmission_distance_cost_500kVac_nodal.csv")
const HVDC_CAPACITY_FILE = joinpath("transmission", "transmission_capacity_init_nonAC_nodal.csv")
const HVDC_COST_FILE = joinpath("transmission", "transmission_distance_cost_500kVdc_nodal.csv")

# Strip the leading `b` from a `bXXX`-form bus id string, e.g. `"b101"` -> `101`.
function _bus_number(bus_label::AbstractString)
    return parse(Int, lstrip(==('b'), String(bus_label)))
end

function _add_ac_transport_technologies!(
    doc::PortfolioCase,
    source::AbstractString,
    inv_idx::InvestmentTopologyIndex,
)
    capacity = CSV.read(joinpath(source, AC_CAPACITY_FILE), DataFrame)
    all(capacity[!, "MW_f0"] .== capacity[!, "MW_r0"]) ||
        error("$AC_CAPACITY_FILE: expected MW_f0 == MW_r0 on every row")

    summed_capacity = sort(
        combine(groupby(capacity, ["From_Bus", "To_Bus"]), "MW_f0" => sum => "MW_f0"),
        ["From_Bus", "To_Bus"],
    )

    cost = CSV.read(joinpath(source, AC_COST_FILE), DataFrame)
    cost_group_sizes = combine(groupby(cost, ["r", "rr"]), nrow => :n)
    any(cost_group_sizes[!, :n] .> 1) &&
        error("$AC_COST_FILE: expected exactly one row per (r, rr) pair")
    cost_by_pair = Dict{Tuple{String, String}, Float64}(
        (String(row["r"]), String(row["rr"])) => Float64(row["USD2004perMW"]) for row in eachrow(cost)
    )

    technology_id_by_bus_pair = Dict{Tuple{Int, Int}, Int}()
    for row in eachrow(summed_capacity)
        from_bus_label = String(row["From_Bus"])
        to_bus_label = String(row["To_Bus"])
        pair = (from_bus_label, to_bus_label)
        haskey(cost_by_pair, pair) || error("$AC_COST_FILE: no cost row for pair $pair")

        start_bus = _bus_number(from_bus_label)
        end_bus = _bus_number(to_bus_label)

        technology = PD.NodalACTransportTechnology(;
            id = next_id!(doc),
            name = "AC_$(start_bus)_$(end_bus)",
            available = true,
            power_systems_type = "Line",
            start_node = inv_idx.node_id_by_bus_number[start_bus],
            end_node = inv_idx.node_id_by_bus_number[end_bus],
            capacity_limits = PD.MinMax(; min = 0.0, max = Float64(row["MW_f0"])),
            # resistance/reactance/voltage/unit_size carry a 0.0 default in the schema, but the
            # Julia generator drops scalar defaults where the Python one honors them -- so
            # Julia would emit nothing here and Python 0.0. Set explicitly so both languages
            # write the same document.
            resistance = 0.0,
            reactance = 0.0,
            voltage = 0.0,
            unit_size = 0.0,
            capital_costs = capital_costs_for(flat_linear_value_curve(cost_by_pair[pair])),
            financial_data = transport_financial_data(),
        )
        technology_id = add!(doc, technology)
        technology_id_by_bus_pair[(start_bus, end_bus)] = technology_id
    end

    return technology_id_by_bus_pair
end

function _add_hvdc_transport_technologies!(
    doc::PortfolioCase,
    source::AbstractString,
    inv_idx::InvestmentTopologyIndex,
)
    capacity = CSV.read(joinpath(source, HVDC_CAPACITY_FILE), DataFrame)
    cost = CSV.read(joinpath(source, HVDC_COST_FILE), DataFrame)
    (nrow(capacity) == 1 && nrow(cost) == 1) || error(
        "expected exactly 1 row in each of $(repr(HVDC_CAPACITY_FILE)) and $(repr(HVDC_COST_FILE))",
    )

    capacity_row = capacity[1, :]
    cost_row = cost[1, :]
    (String(capacity_row["r"]), String(capacity_row["rr"])) == (String(cost_row["r"]), String(cost_row["rr"])) ||
        error("$HVDC_CAPACITY_FILE and $HVDC_COST_FILE: (r, rr) pairs do not match")

    start_bus = _bus_number(String(capacity_row["r"]))
    end_bus = _bus_number(String(capacity_row["rr"]))

    technology = PD.NodalHVDCTransportTechnology(;
        id = next_id!(doc),
        name = "HVDC_$(start_bus)_$(end_bus)",
        available = true,
        power_systems_type = "TwoTerminalGenericHVDCLine",
        start_node = inv_idx.node_id_by_bus_number[start_bus],
        end_node = inv_idx.node_id_by_bus_number[end_bus],
        capacity_limits = PD.MinMax(; min = 0.0, max = Float64(capacity_row["MW"])),
        capital_costs = capital_costs_for(
            flat_linear_value_curve(Float64(cost_row["USD2004perMW"])),
        ),
        line_loss = nothing,
        financial_data = transport_financial_data(),
    )
    technology_id = add!(doc, technology)
    return Dict{Tuple{Int, Int}, Int}((start_bus, end_bus) => technology_id)
end

"""
    add_transport_technologies!(doc, source::AbstractString,
        inv_idx::InvestmentTopologyIndex) -> (ac_id_by_bus_pair, hvdc_id_by_bus_pair)

Add every `NodalACTransportTechnology` (one per unique existing AC corridor, 108 total) and the
one `NodalHVDCTransportTechnology` to `doc`. Returns `(ac_id_by_bus_pair, hvdc_id_by_bus_pair)`,
each a `Dict{Tuple{Int, Int}, Int}` keyed by `(start_bus_number, end_bus_number)`.
"""
function add_transport_technologies!(
    doc::PortfolioCase,
    source::AbstractString,
    inv_idx::InvestmentTopologyIndex,
)
    ac_id_by_bus_pair = _add_ac_transport_technologies!(doc, source, inv_idx)
    hvdc_id_by_bus_pair = _add_hvdc_transport_technologies!(doc, source, inv_idx)
    return ac_id_by_bus_pair, hvdc_id_by_bus_pair
end
