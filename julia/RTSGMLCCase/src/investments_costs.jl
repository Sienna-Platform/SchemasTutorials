# The external-cost surface for investments technology candidates (R37): one capital-cost curve
# and one `TechnologyFinancialData` per `SupplyTechnology` class (E2/JE2). Ported from Python's
# `investments/costs.py`.
#
# The figures in `CAPITAL_COST_PER_MW` and `financial_data_for` are **illustrative
# order-of-magnitude values approximating published NREL ATB ranges** (NREL 2024 Annual
# Technology Baseline, Moderate scenario, ~2030 vintage) -- no live ATB data pull was performed
# this session. They are plausible for an RTS-scale, technology-agnostic worked example, nothing
# more; a reader who needs verified numbers should replace this table from the actual ATB
# spreadsheet.

# USD/MW, flat marginal capital cost (LINEAR, zero intercept). One comment per entry names the
# class it's for; figures are order-of-magnitude picks, not a cited ATB lookup.
const CAPITAL_COST_PER_MW = Dict{String, Float64}(
    "gas-cc" => 1_150_000.0,      # gas-cc: combined-cycle gas turbine
    "gas-ct" => 850_000.0,        # gas-ct: simple-cycle gas combustion turbine
    # o-g-s: oil-fired CT/STEAM peaker; no ATB band given for this class -- interpolated between
    # gas-ct and coalolduns since the source class spans both Unit Types (CT and STEAM).
    "o-g-s" => 1_200_000.0,
    "coalolduns" => 4_500_000.0,  # coalolduns: old-unscrubbed-coal candidate slot (not a realistic new-build forecast)
    "nuclear" => 7_500_000.0,     # nuclear
    "hydED" => 5_000_000.0,       # hydED: existing-dam hydro upgrade/expansion
    "hydEND" => 5_000_000.0,      # hydEND: non-dam (run-of-river) hydro
    "upv" => 1_000_000.0,         # upv: utility-scale PV
    "wind-ons" => 1_450_000.0,    # wind-ons: onshore wind
)

"""
    flat_linear_value_curve(proportional_term::Float64) -> PD.ValueCurve

Return a flat `INPUT_OUTPUT`/`LINEAR` value curve with the given marginal rate (USD/MW or
USD/MWh) and a zero intercept. The shared building block behind [`capital_cost_curve`](@ref)
below.
"""
function flat_linear_value_curve(proportional_term::Float64)
    return PD.ValueCurve(
        PD.InputOutputCurve(;
            function_data = PD.InputOutputCurveFunctionData(
                PD.LinearFunctionData(; constant_term = 0.0, proportional_term = proportional_term),
            ),
        ),
    )
end

"""
    capital_cost_curve(tech_class::AbstractString) -> PD.ValueCurve

Return a flat `INPUT_OUTPUT`/`LINEAR` capital-cost curve (`CAPITAL_COST_PER_MW[tech_class]`
USD/MW, zero intercept) for `tech_class`.
"""
function capital_cost_curve(tech_class::AbstractString)
    haskey(CAPITAL_COST_PER_MW, tech_class) ||
        error("tech class $(repr(tech_class)): no entry in CAPITAL_COST_PER_MW")
    return flat_linear_value_curve(CAPITAL_COST_PER_MW[tech_class])
end

"""
    financial_data_for(tech_class::AbstractString) -> PD.TechnologyFinancialData

Return a fresh `TechnologyFinancialData` for `tech_class`.

Values are identical across every class today (25yr recovery, 50% debt fraction,
mid-single-digit debt rate, low-double-digit ROE, 21% (US statutory) tax rate) -- a distinct
instance is minted per call, one per class, in case a future edit adds per-class variation.
"""
function financial_data_for(_tech_class::AbstractString)
    return PD.TechnologyFinancialData(;
        capital_recovery_period = 25,
        technology_base_year = 2030,
        debt_fraction = 0.5,
        debt_rate = 0.045,
        return_on_equity = 0.11,
        tax_rate = 0.21,
    )
end

# E3/JE3: the one illustrative StorageTechnology candidate (a 4-hour lithium-ion battery).
# Power-capacity legs (charge/discharge, USD/MW) and the energy-capacity leg (USD/MWh) are split
# so that a 4-hour duration reconstructs to roughly $1,600/kW total installed cost
# (200_000 * 2 legs + 300_000 * 4 hours = 1_600_000 USD/MW) -- the same ballpark as NREL ATB's
# ~$1,590/kW 2030-moderate 4-hour utility battery figure. Same "no live ATB pull performed"
# caveat as CAPITAL_COST_PER_MW.
const BATTERY_CAPITAL_COST_PER_MW_CHARGE = 200_000.0
const BATTERY_CAPITAL_COST_PER_MW_DISCHARGE = 200_000.0
const BATTERY_CAPITAL_COST_PER_MWH_ENERGY = 300_000.0

"""
    battery_capital_costs() -> PD.StorageCapitalCost

Return the `StorageCapitalCost` for E3/JE3's one illustrative 4-hour lithium-ion
`StorageTechnology` candidate.

The three legs travel together in one object rather than as three sibling fields:
`StorageTechnology.capital_costs` is a single `StorageCapitalCost`, which is also where
`interconnection_cost` lives, set to 0.0 because no dataset figure backs one.

The schema gives `interconnection_cost` a 0.0 default, but the Julia generator emits it as a
plain required `Float64` while the Python one honors the default -- so Julia must pass it and
Python need not. Passing it explicitly here keeps the two languages' output identical either way.
"""
function battery_capital_costs()
    return PD.StorageCapitalCost(;
        charge_capital_cost = flat_linear_value_curve(BATTERY_CAPITAL_COST_PER_MW_CHARGE),
        discharge_capital_cost = flat_linear_value_curve(BATTERY_CAPITAL_COST_PER_MW_DISCHARGE),
        energy_capital_cost = flat_linear_value_curve(BATTERY_CAPITAL_COST_PER_MWH_ENERGY),
        interconnection_cost = 0.0,
    )
end

"""
    capital_costs_for(capital_cost::PD.ValueCurve) -> PD.CapitalCost

Wrap a capital-cost curve in the `CapitalCost` a technology's `capital_costs` field actually
takes. The curve alone is not the field: `CapitalCost` pairs it with `interconnection_cost`,
left at its 0.0 default here because no dataset figure backs one.
"""
capital_costs_for(capital_cost) =
    PD.CapitalCost(; capital_cost = capital_cost, interconnection_cost = 0.0)

"""
    battery_operation_cost() -> PD.StorageCost

Return a zero-cost `StorageCost` for the illustrative battery candidate. No dataset or ATB
figure backs a nonzero fixed/variable/startup/shutdown cost here; matches the same all-zero
convention `generation.jl`'s `_storage_operation_cost` already uses for the operations-side
`EnergyReservoirStorage`.
"""
function battery_operation_cost()
    return PD.StorageCost(;
        fixed = 0.0,
        shut_down = 0.0,
        start_up = PD.StorageCostStartUp(0.0),
        energy_shortage_cost = 0.0,
        energy_surplus_cost = 0.0,
    )
end

"""
    transport_financial_data() -> PD.TechnologyFinancialData

Return a fresh `TechnologyFinancialData` for an AC or HVDC transport candidate (E3/JE3).

`capital_recovery_period = 40` is genuinely dataset-sourced -- `scalars.csv`'s `trans_crp` row:
`trans_crp,40,--years-- transmission capital recovery period (financial lifetime / evaluation
period). Applied to transmission lines, AC/DC converters, and substations.` The other 5 fields
have no transmission-specific source in this dataset; they carry the same illustrative values
and framing as [`financial_data_for`](@ref).
"""
function transport_financial_data()
    return PD.TechnologyFinancialData(;
        capital_recovery_period = 40,
        technology_base_year = 2030,
        debt_fraction = 0.5,
        debt_rate = 0.045,
        return_on_equity = 0.11,
        tax_rate = 0.21,
    )
end
