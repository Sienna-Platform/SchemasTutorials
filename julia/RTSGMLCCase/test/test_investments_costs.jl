# Unwraps a `PowerOpenAPIModels.ValueCurve` down to its `LinearFunctionData`, asserting the shape at each level
# (INPUT_OUTPUT / LINEAR) rather than assuming it.
function _linear_function_data(curve::PowerOpenAPIModels.ValueCurve)
    io_curve = curve.value
    @test io_curve isa PowerOpenAPIModels.InputOutputCurve
    @test io_curve.curve_type == "INPUT_OUTPUT"
    function_data = io_curve.function_data.value
    @test function_data isa PowerOpenAPIModels.LinearFunctionData
    @test function_data.function_type == "LINEAR"
    return function_data
end

@testset "capital cost per mw covers every candidate class" begin
    @test Set(keys(RTSGMLCCase.CAPITAL_COST_PER_MW)) == Set(keys(RTSGMLCCase.POWER_SYSTEMS_TYPE_BY_CLASS))
end

@testset "capital cost values are plausible order of magnitude" begin
    for (tech_class, cost) in RTSGMLCCase.CAPITAL_COST_PER_MW
        @test cost > 0
        @test 1e5 < cost < 1e7
    end
end

@testset "capital cost curve is a flat linear input-output curve" begin
    for (tech_class, expected_cost) in RTSGMLCCase.CAPITAL_COST_PER_MW
        curve = RTSGMLCCase.capital_cost_curve(tech_class)
        function_data = _linear_function_data(curve)
        @test function_data.constant_term == 0.0
        @test function_data.proportional_term == expected_cost
    end
end

@testset "financial data for every class is fully populated and a fresh instance" begin
    instances = [RTSGMLCCase.financial_data_for(tech_class) for tech_class in keys(RTSGMLCCase.POWER_SYSTEMS_TYPE_BY_CLASS)]
    @test length(instances) == 9
    # Distinct objects (one instance per class), even though values may be shared across classes.
    @test length(Set(objectid(instance) for instance in instances)) == 9

    for instance in instances
        @test instance.capital_recovery_period isa Int
        @test instance.capital_recovery_period > 0
        @test instance.technology_base_year isa Int
        @test 0.0 <= instance.debt_fraction <= 1.0
        @test instance.debt_rate > 0.0
        @test instance.return_on_equity > 0.0
        @test 0.0 <= instance.tax_rate <= 1.0
    end
end

@testset "flat_linear_value_curve shape" begin
    curve = RTSGMLCCase.flat_linear_value_curve(123.0)
    function_data = _linear_function_data(curve)
    @test function_data.constant_term == 0.0
    @test function_data.proportional_term == 123.0
end

@testset "capital_cost_curve is built from flat_linear_value_curve" begin
    for (tech_class, expected_cost) in RTSGMLCCase.CAPITAL_COST_PER_MW
        a = _linear_function_data(RTSGMLCCase.capital_cost_curve(tech_class))
        b = _linear_function_data(RTSGMLCCase.flat_linear_value_curve(expected_cost))
        @test a.constant_term == b.constant_term
        @test a.proportional_term == b.proportional_term
    end
end

@testset "capital_cost_curve raises for an unknown class" begin
    err = nothing
    try
        RTSGMLCCase.capital_cost_curve("not-a-real-class")
    catch caught
        err = caught
    end
    @test err !== nothing
    message = sprint(showerror, err)
    @test occursin("not-a-real-class", message)
end
