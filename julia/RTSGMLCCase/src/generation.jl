using CSV: CSV
using DataFrames: DataFrame

# `Min Up/Down Time Hr` are hours in gen.csv; `time_limits` is minutes, a unit-system fact about
# the field (shared with every family that carries it), not a thermal-only quirk.
const GENERATION_MINUTES_PER_HOUR = 60.0

# `SynchronousCondenser`'s `Base MVA` is 0.0 for every row in gen.csv; 100.0 is a hardcoded
# convention, not a derived value.
const SYNC_COND_BASE_POWER = 100.0

# Ported from Python's `PRIME_MOVER_BY_UNIT_TYPE` verbatim. RTPV and STORAGE are looked up here
# only for documentation parity with the Python dict -- their one builder each hardcodes the
# value directly (as Python's does) rather than looking it up, since each maps only one Unit
# Type. SYNC_COND has no entry: `SynchronousCondenser` carries no `prime_mover_type` field.
const PRIME_MOVER_BY_UNIT_TYPE = Dict{String, PD.PrimeMovers}(
    "PV" => PD.PrimeMovers("PVe"),
    "RTPV" => PD.PrimeMovers("PVe"),
    "WIND" => PD.PrimeMovers("WT"),
    "CSP" => PD.PrimeMovers("CP"),
    "HYDRO" => PD.PrimeMovers("HY"),
    "ROR" => PD.PrimeMovers("HY"),
    "STORAGE" => PD.PrimeMovers("BA"),
    "NUCLEAR" => PD.PrimeMovers("ST"),
    "STEAM" => PD.PrimeMovers("ST"),
    "CT" => PD.PrimeMovers("CT"),
    "CC" => PD.PrimeMovers("CC"),
)

const THERMAL_FUEL = Dict{String, PD.ThermalFuels}(
    "Oil" => PD.ThermalFuels("DISTILLATE_FUEL_OIL"),
    "Coal" => PD.ThermalFuels("COAL"),
    "NG" => PD.ThermalFuels("NATURAL_GAS"),
    "Nuclear" => PD.ThermalFuels("NUCLEAR"),
)

# gen.csv `Unit Type` -> target component type name, ported from Python's `UNIT_TYPE_TO_MODEL`
# verbatim (12 entries, not 11 -- ROR, run-of-river, maps to HydroDispatch alongside HYDRO).
# Public: `timeseries.jl` uses this (via `unit_type_target`) to resolve `owner_type` for
# `Category == "Generator"` pointer rows.
const UNIT_TYPE_TO_TARGET = Dict{String, String}(
    "NUCLEAR" => "ThermalStandard",
    "STEAM" => "ThermalStandard",
    "CT" => "ThermalStandard",
    "CC" => "ThermalStandard",
    "WIND" => "RenewableDispatch",
    "PV" => "RenewableDispatch",
    "CSP" => "RenewableDispatch",
    "RTPV" => "RenewableNonDispatch",
    "HYDRO" => "HydroDispatch",
    "ROR" => "HydroDispatch",
    "SYNC_COND" => "SynchronousCondenser",
    "STORAGE" => "EnergyReservoirStorage",
)

"""
    unit_type_target(unit_type::AbstractString) -> String

Return the target component type name for a gen.csv `Unit Type`, mirroring Python's
`unit_type_target`. Errors if `unit_type` is not in [`UNIT_TYPE_TO_TARGET`](@ref).
"""
function unit_type_target(unit_type::AbstractString)
    haskey(UNIT_TYPE_TO_TARGET, unit_type) || error("unmapped Unit Type $(repr(unit_type))")
    return UNIT_TYPE_TO_TARGET[unit_type]
end

# gen.csv's Output_pct_4/HR_incr_4 are absent ("NA") for units with fewer than four heat-rate
# blocks (e.g. 101_CT_1 has 4 x-coords but only 3 y-coords). CSV.jl's own handling of "NA" isn't
# assumed to take one fixed form -- cover a missing value, a float NaN, and the literal string.
function _is_present(value)
    ismissing(value) && return false
    if value isa AbstractFloat
        return !isnan(value)
    end
    if value isa AbstractString
        return value != "NA"
    end
    return true
end

function _linear_input_output_curve(proportional_term::Float64)
    return PD.InputOutputCurve(;
        curve_type = "INPUT_OUTPUT",
        function_data = PD.InputOutputCurveFunctionData(
            PD.LinearFunctionData(;
                constant_term = 0.0,
                function_type = "LINEAR",
                proportional_term = proportional_term,
            ),
        ),
    )
end

# Nested per R-verified layout: operation_cost -> variable_operation_cost (a FuelCurve) ->
# value_curve (an INCREMENTAL curve) -> function_data (PIECEWISE_STEP). `curve_type` and
# `function_type` are separate discriminators on separate nested objects -- easy to conflate.
function _thermal_operation_cost(row, uid::AbstractString, pmax::Float64)
    x_coords = Float64[]
    for k in 0:4
        value = row["Output_pct_$k"]
        _is_present(value) || continue
        push!(x_coords, Float64(value) * pmax)
    end
    y_coords = Float64[]
    for k in 1:4
        value = row["HR_incr_$k"]
        _is_present(value) || continue
        push!(y_coords, Float64(value))
    end
    isempty(x_coords) && error("gen.csv row $(repr(uid)): no Output_pct_k values present")

    fuel_price = Float64(row["Fuel Price \$/MMBTU"])
    # No x1000 factor here -- HR_avg_0 and x_coords[1] are already in the units this field wants.
    initial_input = Float64(row["HR_avg_0"]) * x_coords[1]

    value_curve = PD.ValueCurve(
        PD.IncrementalCurve(;
            curve_type = "INCREMENTAL",
            function_data = PD.IncrementalCurveFunctionData(
                PD.PiecewiseStepData(;
                    function_type = "PIECEWISE_STEP",
                    x_coords = x_coords,
                    y_coords = y_coords,
                ),
            ),
            initial_input = initial_input,
        ),
    )

    fuel_curve = PD.FuelCurve(;
        fuel_cost = fuel_price / 1000.0,
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        variable_cost_type = "FUEL",
        value_curve = value_curve,
        vom_cost = _linear_input_output_curve(Float64(row["VOM"])),
    )

    start_up = Float64(row["Non Fuel Start Cost \$"]) + Float64(row["Start Heat Cold MBTU"]) * fuel_price

    thermal_cost = PD.ThermalGenerationCost(;
        cost_type = "THERMAL",
        fixed = 0.0,
        shut_down = Float64(row["Non Fuel Shutdown Cost \$"]),
        start_up = PD.ThermalGenerationCostStartUp(start_up),
        variable_operation_cost = PD.ProductionVariableCostCurve(fuel_curve),
    )

    return PD.ThermalStandardOperationCost(thermal_cost)
end

# Builds one `ThermalStandard` from a gen.csv row. Covers all four thermal `Unit Type`s
# (NUCLEAR, STEAM, CT, CC) -- the split between them is only `prime_mover_type`/`fuel`.
# `_storage_row` is unused (only `_build_energy_reservoir_storage` needs it); it stays in the
# signature so every entry in `GENERATOR_BUILDERS` shares one call shape.
function _build_thermal_standard(doc::PD.SystemDocument, row, bus_id::Int, _storage_row)
    uid = String(row["GEN UID"])
    unit_type = String(row["Unit Type"])
    fuel_name = String(row["Fuel"])
    haskey(THERMAL_FUEL, fuel_name) ||
        error("gen.csv row $(repr(uid)): unmapped Fuel $(repr(fuel_name))")
    fuel = THERMAL_FUEL[fuel_name]

    ramp = Float64(row["Ramp Rate MW/Min"])
    pmax = Float64(row["PMax MW"])
    qmax = Float64(row["QMax MVAR"])

    return PD.ThermalStandard(;
        id = PD.next_id!(doc),
        name = uid,
        available = true,
        # RTS carries no initial-commitment state, so "all units online at t0" is a tutorial
        # convention, not source data -- pinned so Julia and Python emit identical output.
        status = PD.OperationalStates("ONLINE"),
        # `must_run` was replaced by `commitment_mode`; COMMITTED is the field's own default
        # and the closest analogue for an online, dispatchable thermal unit. Matches the
        # Python tutorial exactly.
        commitment_mode = PD.CommitmentModes("COMMITTED"),
        bus = bus_id,
        active_power = Float64(row["MW Inj"]),
        reactive_power = Float64(row["MVAR Inj"]),
        rating = hypot(pmax, qmax),
        active_power_limits = PD.MinMax(; min = Float64(row["PMin MW"]), max = pmax),
        reactive_power_limits = PD.MinMax(; min = Float64(row["QMin MVAR"]), max = qmax),
        ramp_limits = PD.UpDown(; up = ramp, down = ramp),
        operation_cost = _thermal_operation_cost(row, uid, pmax),
        base_power = Float64(row["Base MVA"]),
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        time_limits = PD.UpDown(;
            up = Float64(row["Min Up Time Hr"]) * GENERATION_MINUTES_PER_HOUR,
            down = Float64(row["Min Down Time Hr"]) * GENERATION_MINUTES_PER_HOUR,
        ),
        prime_mover_type = PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        fuel = fuel,
        time_at_status = 600000.0,
    )
end

# RenewableDispatch's operation cost: a plain `CostCurve` (COST, not FUEL), unlike thermal's
# `FuelCurve` -- confirmed against `model_RenewableGenerationCost.jl`'s `variable_operation_cost`
# field type.
function _renewable_operation_cost(row)
    cost_curve = PD.CostCurve(;
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        value_curve = PD.ValueCurve(_linear_input_output_curve(0.0)),
        variable_cost_type = "COST",
        vom_cost = _linear_input_output_curve(Float64(row["VOM"])),
    )
    renewable_cost = PD.RenewableGenerationCost(;
        cost_type = "RENEWABLE",
        fixed = 0.0,
        variable_operation_cost = cost_curve,
    )
    return PD.RenewableDispatchOperationCost(renewable_cost)
end

# WIND, PV, CSP -- rating and base_power both take `Base MVA` (which coincides with `PMax MW`
# in every row).
function _build_renewable_dispatch(doc::PD.SystemDocument, row, bus_id::Int, _storage_row)
    unit_type = String(row["Unit Type"])
    base_power = Float64(row["Base MVA"])

    return PD.RenewableDispatch(;
        id = PD.next_id!(doc),
        name = String(row["GEN UID"]),
        available = true,
        bus = bus_id,
        active_power = Float64(row["MW Inj"]),
        reactive_power = Float64(row["MVAR Inj"]),
        rating = base_power,
        prime_mover_type = PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        reactive_power_limits = PD.MinMax(;
            min = Float64(row["QMin MVAR"]),
            max = Float64(row["QMax MVAR"]),
        ),
        power_factor = 1.0,
        operation_cost = _renewable_operation_cost(row),
        base_power = base_power,
        power_units = PD.UnitSystem("NATURAL_UNITS"),
    )
end

# RTPV -- the one Unit Type mapping here, so `prime_mover_type` is the literal "PVe" (matching
# Python's hardcode) rather than a `PRIME_MOVER_BY_UNIT_TYPE` lookup. No `operation_cost` field
# exists on `RenewableNonDispatch` at all.
function _build_renewable_non_dispatch(doc::PD.SystemDocument, row, bus_id::Int, _storage_row)
    base_power = Float64(row["Base MVA"])

    return PD.RenewableNonDispatch(;
        id = PD.next_id!(doc),
        name = String(row["GEN UID"]),
        available = true,
        bus = bus_id,
        active_power = Float64(row["MW Inj"]),
        reactive_power = Float64(row["MVAR Inj"]),
        rating = base_power,
        prime_mover_type = PD.PrimeMovers("PVe"),
        power_factor = 1.0,
        base_power = base_power,
        power_units = PD.UnitSystem("NATURAL_UNITS"),
    )
end

# HydroDispatch's operation cost tree mirrors thermal's (FuelCurve, FUEL) but with an
# INPUT_OUTPUT value curve of HR_avg_0 rather than thermal's PIECEWISE_STEP heat-rate curve --
# confirmed AVERAGE_RATE was considered and rejected against the reference case (every
# HydroDispatch/HydroTurbine there uses INPUT_OUTPUT). Every hydro/ROR row's Fuel Price is 0.0,
# so this fuel_cost/1000.0 unit convention (shared with `_thermal_operation_cost`) is invisible
# today but must stay in step regardless.
function _hydro_operation_cost(row)
    fuel_price = Float64(row["Fuel Price \$/MMBTU"])
    fuel_curve = PD.FuelCurve(;
        fuel_cost = fuel_price / 1000.0,
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        variable_cost_type = "FUEL",
        value_curve = PD.ValueCurve(_linear_input_output_curve(Float64(row["HR_avg_0"]))),
        vom_cost = _linear_input_output_curve(Float64(row["VOM"])),
    )
    hydro_cost = PD.HydroGenerationCost(;
        cost_type = "HYDRO_GEN",
        fixed = 0.0,
        variable_operation_cost = PD.ProductionVariableCostCurve(fuel_curve),
    )
    return PD.HydroDispatchOperationCost(hydro_cost)
end

# HYDRO, ROR -- rating is hypot(PMax, QMax), not Base MVA (unlike the renewable families above).
function _build_hydro_dispatch(doc::PD.SystemDocument, row, bus_id::Int, _storage_row)
    unit_type = String(row["Unit Type"])
    ramp = Float64(row["Ramp Rate MW/Min"])
    pmax = Float64(row["PMax MW"])
    qmax = Float64(row["QMax MVAR"])

    return PD.HydroDispatch(;
        id = PD.next_id!(doc),
        name = String(row["GEN UID"]),
        available = true,
        bus = bus_id,
        active_power = Float64(row["MW Inj"]),
        reactive_power = Float64(row["MVAR Inj"]),
        rating = hypot(pmax, qmax),
        prime_mover_type = PRIME_MOVER_BY_UNIT_TYPE[unit_type],
        active_power_limits = PD.MinMax(; min = Float64(row["PMin MW"]), max = pmax),
        reactive_power_limits = PD.MinMax(; min = Float64(row["QMin MVAR"]), max = qmax),
        ramp_limits = PD.UpDown(; up = ramp, down = ramp),
        time_limits = PD.UpDown(;
            up = Float64(row["Min Up Time Hr"]) * GENERATION_MINUTES_PER_HOUR,
            down = Float64(row["Min Down Time Hr"]) * GENERATION_MINUTES_PER_HOUR,
        ),
        base_power = Float64(row["Base MVA"]),
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        status = PD.OperationalStates("ONLINE"),
        time_at_status = 600000.0,
        operation_cost = _hydro_operation_cost(row),
    )
end

# SYNC_COND -- rating is QMax MVAR (Base MVA is 0.0 for every row in the source, hence
# SYNC_COND_BASE_POWER's hardcoded convention). No prime_mover_type: SynchronousCondenser
# carries no such field.
function _build_synchronous_condenser(doc::PD.SystemDocument, row, bus_id::Int, _storage_row)
    qmax = Float64(row["QMax MVAR"])

    return PD.SynchronousCondenser(;
        id = PD.next_id!(doc),
        name = String(row["GEN UID"]),
        available = true,
        bus = bus_id,
        reactive_power = Float64(row["MVAR Inj"]),
        rating = qmax,
        reactive_power_limits = PD.MinMax(; min = Float64(row["QMin MVAR"]), max = qmax),
        base_power = SYNC_COND_BASE_POWER,
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        active_power_losses = 0.0,
    )
end

function _storage_operation_cost()
    storage_cost = PD.StorageCost(;
        cost_type = "STORAGE",
        fixed = 0.0,
        shut_down = 0.0,
        start_up = PD.StorageCostStartUp(0.0),
        energy_shortage_cost = 0.0,
        energy_surplus_cost = 0.0,
    )
    return PD.EnergyReservoirStorageOperationCost(storage_cost)
end

# STORAGE -- the single `313_STORAGE_1` unit, joined against its `storage.csv` head row for
# `Rating MVA`/`Max Volume GWh`/`Initial Volume GWh`. `Storage Roundtrip Efficiency` (85% in the
# source, on gen.csv not storage.csv) is used directly, split evenly across the charge/discharge
# legs as `sqrt(0.85)` per leg -- the reference case hardcodes 1.0/1.0 instead, which is data
# loss this tutorial does not repeat.
function _build_energy_reservoir_storage(doc::PD.SystemDocument, row, bus_id::Int, storage_row)
    uid = String(row["GEN UID"])
    storage_row === nothing &&
        error("gen.csv row $(repr(uid)): Unit Type STORAGE has no storage.csv row")

    rating = Float64(storage_row["Rating MVA"])
    max_volume_gwh = Float64(storage_row["Max Volume GWh"])
    pump_load = Float64(row["Pump Load MW"])
    leg_efficiency = sqrt(Float64(row["Storage Roundtrip Efficiency"]) / 100.0)

    return PD.EnergyReservoirStorage(;
        id = PD.next_id!(doc),
        name = uid,
        available = true,
        bus = bus_id,
        prime_mover_type = PD.PrimeMovers("BA"),
        storage_technology_type = PD.StorageTech("OTHER_CHEM"),
        storage_capacity = max_volume_gwh * 1000.0,
        energy_units = PD.EnergyUnitBasis("MWH"),
        storage_level_limits = PD.MinMax(; min = 0.0, max = 1.0),
        initial_storage_capacity_level = Float64(storage_row["Initial Volume GWh"]) / max_volume_gwh,
        rating = rating,
        active_power = 0.0,
        # The single storage row can't disambiguate this from `2 * Base MVA` -- both give 100.0
        # here. `Pump Load MW` is chosen as the more semantically apt source (it's literally the
        # charging capacity).
        input_active_power_limits = PD.MinMax(; min = 0.0, max = 2.0 * pump_load),
        output_active_power_limits = PD.MinMax(; min = 0.0, max = rating),
        efficiency = PD.InOut(; in = leg_efficiency, out = leg_efficiency),
        reactive_power = 0.0,
        base_power = Float64(row["Base MVA"]),
        power_units = PD.UnitSystem("NATURAL_UNITS"),
        conversion_factor = 1.0,
        storage_target = 0.0,
        cycle_limits = 10000,
        self_discharge = 0.0,
        standing_loss = 0.0,
        operation_cost = _storage_operation_cost(),
    )
end

# One builder per target component type (`UNIT_TYPE_TO_TARGET`'s values).
const GENERATOR_BUILDERS = Dict{String, Function}(
    "ThermalStandard" => _build_thermal_standard,
    "RenewableDispatch" => _build_renewable_dispatch,
    "RenewableNonDispatch" => _build_renewable_non_dispatch,
    "HydroDispatch" => _build_hydro_dispatch,
    "SynchronousCondenser" => _build_synchronous_condenser,
    "EnergyReservoirStorage" => _build_energy_reservoir_storage,
)

# `storage.csv` is not 1:1 with generators: most rows belong to HYDRO/CSP generators this
# module never looks up, and the one row that matters here (`313_STORAGE_1`) has both a `head`
# and a `tail` entry with identical consumed fields -- `head` is used, for determinism.
function _storage_head_rows(source::AbstractString)
    storage = CSV.read(joinpath(source, "storage.csv"), DataFrame)
    head_rows = Dict{String, Any}()
    for row in eachrow(storage)
        if row["position"] == "head"
            head_rows[String(row["GEN UID"])] = row
        end
    end
    return head_rows
end

"""
    add_generation!(doc, source::AbstractString, idx::TopologyIndex) -> Dict{String,Int}

Add every generator in `source/gen.csv` to `doc`, dispatching to one builder per target
component type (`UNIT_TYPE_TO_TARGET`, `GENERATOR_BUILDERS`). Returns a mapping from `GEN UID`
to the minted component id, iterated in file order.

Raises, naming the offending row, on an unmapped `Unit Type`, an unmapped bus, or (for
`STORAGE`) a missing `storage.csv` row.
"""
function add_generation!(doc::PD.SystemDocument, source::AbstractString, idx::TopologyIndex)
    gen = CSV.read(joinpath(source, "gen.csv"), DataFrame)
    storage_head_by_uid = _storage_head_rows(source)

    generator_id_by_uid = Dict{String, Int}()
    for row in eachrow(gen)
        uid = String(row["GEN UID"])
        unit_type = String(row["Unit Type"])
        haskey(UNIT_TYPE_TO_TARGET, unit_type) ||
            error("gen.csv row $(repr(uid)): unmapped Unit Type $(repr(unit_type))")
        target = UNIT_TYPE_TO_TARGET[unit_type]

        bus_number = Int(row["Bus ID"])
        haskey(idx.bus_id_by_number, bus_number) ||
            error("gen.csv row $(repr(uid)): unmapped bus $bus_number")
        bus_id = idx.bus_id_by_number[bus_number]

        builder = GENERATOR_BUILDERS[target]
        storage_row = get(storage_head_by_uid, uid, nothing)
        component = builder(doc, row, bus_id, storage_row)
        generator_id_by_uid[uid] = add!(doc, component)
    end

    return generator_id_by_uid
end
