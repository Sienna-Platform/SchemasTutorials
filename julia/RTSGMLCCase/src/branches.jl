using CSV: CSV
using DataFrames: DataFrame

# Same 100 MVA base as every other component in this natural-units document (R12a).
const BRANCH_BASE_POWER = 100.0
const NUMBER_OF_TAP_POSITIONS = 33

# The reference case's transformer control-limit and controlled-quantity-limit conventions
# (R22) -- not derivable from the RTS source, adopted because the reference uses them. Wrapped
# in functions rather than shared constants because `MinMax` is a mutable struct; a fresh
# instance per component avoids two transformers ever aliasing the same one.
_angle_limits() = PD.MinMax(; min = -3.1416, max = 3.1416)
_control_limits() = PD.MinMax(; min = 0.9, max = 1.1)
_controlled_quantity_limits() = PD.MinMax(; min = 1.0, max = 1.0)

"""
    arc_id!(doc, cache::Dict{Tuple{Int, Int}, Int}, from_id::Int, to_id::Int) -> Int

Return the id of the `Arc` for `(from_id, to_id)`, minting a fresh one the first time this
ordered pair of *component ids* (already resolved through `TopologyIndex.bus_id_by_number`, not
raw bus numbers) is seen and reusing it thereafter.
"""
function arc_id!(doc::PD.SystemDocument, cache::Dict{Tuple{Int, Int}, Int}, from_id::Int, to_id::Int)
    key = (from_id, to_id)
    haskey(cache, key) && return cache[key]
    arc = PD.Arc(; id = PD.next_id!(doc), from_id = from_id, to_id = to_id)
    id = add!(doc, arc)
    cache[key] = id
    return id
end

# Resolve a source bus number to its component id, raising with context rather than a bare
# KeyError -- `label` and `uid` name which branch and which endpoint failed.
function _resolved_bus_id(idx::TopologyIndex, bus_number::Int, uid::AbstractString, label::AbstractString)
    haskey(idx.bus_id_by_number, bus_number) ||
        error("branch $uid: unmapped $label-bus $bus_number: not in topology index")
    return idx.bus_id_by_number[bus_number]
end

"""
    add_branches!(doc, source::AbstractString, idx::TopologyIndex) -> Nothing

Add `Arc`, `Line`, `TransformerCircuit`, `TwoWindingTransformer`, and
`TwoTerminalGenericHVDCLine` components read from `source/branch.csv` and `source/dc_branch.csv`
to `doc`.

A branch is a transformer when its two buses have different base voltages -- physical and
self-documenting, and equivalent to `Tr Ratio` not in `{0.0, 1.0}`. Branch `C35` steps 230 kV to
230 kV with `Tr Ratio` exactly `1.0`: an identity element between equal base voltages, not a
transformer, so the naive "`Tr Ratio != 0` means transformer" rule misclassifies it (R21). Both
formulations must agree for every row; this function raises loudly if they ever disagree.

Every transformer becomes a `TransformerCircuit` (the electrical parameters; it has no `name`)
plus a `TwoWindingTransformer` (the named component, referencing the circuit by id). Every
component sets `power_units = "NATURAL_UNITS"` and an explicit `base_power`; branch components
also set `parameter_units = "COMPONENT_BASE"` (and `TwoWindingTransformer` sets
`admittance_units = "COMPONENT_BASE"`) so per-unit impedances coexist with a natural-units case
(R22).
"""
function add_branches!(doc::PD.SystemDocument, source::AbstractString, idx::TopologyIndex)
    bus = CSV.read(joinpath(source, "bus.csv"), DataFrame)
    base_kv_by_number = Dict(Int(row["Bus ID"]) => Float64(row["BaseKV"]) for row in eachrow(bus))

    arc_cache = Dict{Tuple{Int, Int}, Int}()

    branch = CSV.read(joinpath(source, "branch.csv"), DataFrame)
    for row in eachrow(branch)
        uid = String(row["UID"])
        from_bus = Int(row["From Bus"])
        to_bus = Int(row["To Bus"])

        haskey(base_kv_by_number, from_bus) || error("branch $uid: unmapped from-bus $from_bus in bus.csv")
        haskey(base_kv_by_number, to_bus) || error("branch $uid: unmapped to-bus $to_bus in bus.csv")
        from_kv = base_kv_by_number[from_bus]
        to_kv = base_kv_by_number[to_bus]
        tr_ratio = Float64(row["Tr Ratio"])

        is_transformer = from_kv != to_kv
        tr_ratio_says_transformer = !(tr_ratio in (0.0, 1.0))
        if is_transformer != tr_ratio_says_transformer
            error(
                "branch $uid: voltage-based classification ($is_transformer) disagrees with " *
                "the Tr Ratio rule ($tr_ratio_says_transformer) -- from_kv=$from_kv, " *
                "to_kv=$to_kv, tr_ratio=$tr_ratio",
            )
        end

        from_id = _resolved_bus_id(idx, from_bus, uid, "from")
        to_id = _resolved_bus_id(idx, to_bus, uid, "to")
        arc = arc_id!(doc, arc_cache, from_id, to_id)

        rating = Float64(row["Cont Rating"])
        rating_b = Float64(row["LTE Rating"])
        rating_c = Float64(row["STE Rating"])
        r = Float64(row["R"])
        x = Float64(row["X"])

        if is_transformer
            circuit = PD.TransformerCircuit(;
                id = PD.next_id!(doc),
                available = true,
                arc = arc,
                tap = tr_ratio,
                alpha = 0.0,
                parameter_units = PD.ImpedanceUnitBasis("COMPONENT_BASE"),
                r = r,
                x = x,
                control_objective = PD.TransformerControlObjective("FIXED"),
                control_limits = _control_limits(),
                controlled_quantity_limits = _controlled_quantity_limits(),
                regulated_bus_number = 0,
                number_of_tap_positions = NUMBER_OF_TAP_POSITIONS,
                rating = rating,
                rating_b = rating_b,
                rating_c = rating_c,
                active_power_flow = 0.0,
                reactive_power_flow = 0.0,
                base_power = BRANCH_BASE_POWER,
                power_units = PD.UnitSystem("NATURAL_UNITS"),
                base_voltage_primary = from_kv,
                base_voltage_secondary = to_kv,
            )
            circuit_id = add!(doc, circuit)

            transformer = PD.TwoWindingTransformer(;
                id = PD.next_id!(doc),
                name = uid,
                circuit = circuit_id,
                magnetizing_shunt = PD.ComplexNumber(; real = 0.0, imag = 0.0),
                shunt_location = PD.TwoWindingTransformerShuntLocation("PRIMARY"),
                admittance_units = PD.AdmittanceUnitBasis("COMPONENT_BASE"),
            )
            add!(doc, transformer)
        else
            b_half = Float64(row["B"]) / 2.0
            line = PD.Line(;
                id = PD.next_id!(doc),
                name = uid,
                available = true,
                active_power_flow = 0.0,
                reactive_power_flow = 0.0,
                arc = arc,
                r = r,
                x = x,
                base_power = BRANCH_BASE_POWER,
                power_units = PD.UnitSystem("NATURAL_UNITS"),
                parameter_units = PD.ImpedanceUnitBasis("COMPONENT_BASE"),
                b = PD.FromTo(; from = b_half, to = b_half),
                rating = rating,
                rating_b = rating_b,
                rating_c = rating_c,
                angle_limits = _angle_limits(),
                g = PD.FromTo(; from = 0.0, to = 0.0),
            )
            add!(doc, line)
        end
    end

    dc_branch = CSV.read(joinpath(source, "dc_branch.csv"), DataFrame)
    for row in eachrow(dc_branch)
        uid = String(row["UID"])
        from_bus = Int(row["From Bus"])
        to_bus = Int(row["To Bus"])
        from_id = _resolved_bus_id(idx, from_bus, uid, "from")
        to_id = _resolved_bus_id(idx, to_bus, uid, "to")
        arc = arc_id!(doc, arc_cache, from_id, to_id)

        mw_load = Float64(row["MW Load"])
        margin = Float64(row["Margin"])

        hvdc = PD.TwoTerminalGenericHVDCLine(;
            id = PD.next_id!(doc),
            name = uid,
            available = true,
            active_power_flow = 0.0,
            arc = arc,
            active_power_limits_from = PD.MinMax(; min = -mw_load, max = mw_load),
            active_power_limits_to = PD.MinMax(; min = -mw_load, max = mw_load),
            reactive_power_limits_from = PD.MinMax(; min = 0.0, max = 100.0),
            reactive_power_limits_to = PD.MinMax(; min = 0.0, max = 100.0),
            # `loss` is a `LossCurve` -- the curve plus its own `power_units` -- not a bare
            # curve, and the curve itself rides inside a generated `LossValueCurve` oneOf
            # wrapper. Mirrors the Python side's `LossCurve(power_units=..., value_curve=...)`.
            loss = PD.LossCurve(;
                power_units = PD.UnitSystem("NATURAL_UNITS"),
                value_curve = PD.LossValueCurve(
                    PD.InputOutputCurve(;
                        curve_type = "INPUT_OUTPUT",
                        function_data = PD.InputOutputCurveFunctionData(
                            PD.LinearFunctionData(;
                                constant_term = 0.0,
                                function_type = "LINEAR",
                                proportional_term = margin,
                            ),
                        ),
                    ),
                ),
            ),
            base_power = BRANCH_BASE_POWER,
            power_units = PD.UnitSystem("NATURAL_UNITS"),
        )
        add!(doc, hvdc)
    end

    return nothing
end
