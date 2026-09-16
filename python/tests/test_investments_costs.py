import warnings

from rts_gmlc_case.investments.costs import (
    BATTERY_CAPITAL_COST_PER_MW_CHARGE,
    BATTERY_CAPITAL_COST_PER_MW_DISCHARGE,
    BATTERY_CAPITAL_COST_PER_MWH_ENERGY,
    CAPITAL_COST_PER_MW,
    battery_capital_costs,
    battery_operation_cost,
    capital_cost_curve,
    financial_data_for,
    flat_linear_value_curve,
    transport_financial_data,
)
from rts_gmlc_case.investments.technologies import POWER_SYSTEMS_TYPE_BY_CLASS


def test_capital_cost_per_mw_covers_every_candidate_class():
    assert set(CAPITAL_COST_PER_MW) == set(POWER_SYSTEMS_TYPE_BY_CLASS)


def test_capital_cost_values_are_plausible_order_of_magnitude():
    # All 9 candidate classes have a positive, million-dollar-scale USD/MW
    # figure -- not zero, not a stray unit-mismatched value.
    for tech_class, cost in CAPITAL_COST_PER_MW.items():
        assert cost > 0, tech_class
        assert 1e5 < cost < 1e7, f"{tech_class}: {cost} out of plausible USD/MW range"


def test_capital_cost_curve_is_a_flat_linear_input_output_curve():
    for tech_class, expected_cost in CAPITAL_COST_PER_MW.items():
        curve = capital_cost_curve(tech_class)
        dumped = curve.model_dump(mode="json")
        assert dumped["curve_type"] == "INPUT_OUTPUT"
        assert dumped["function_data"]["function_type"] == "LINEAR"
        assert dumped["function_data"]["constant_term"] == 0.0
        assert dumped["function_data"]["proportional_term"] == expected_cost


def test_financial_data_for_every_class_is_fully_populated_and_a_fresh_instance():
    instances = [financial_data_for(tech_class) for tech_class in POWER_SYSTEMS_TYPE_BY_CLASS]
    assert len(instances) == 9
    # Distinct objects (one instance per class), even though values may be
    # shared across classes.
    assert len({id(instance) for instance in instances}) == 9

    for instance in instances:
        assert isinstance(instance.capital_recovery_period, int)
        assert instance.capital_recovery_period > 0
        assert isinstance(instance.technology_base_year, int)
        assert 0.0 <= instance.debt_fraction <= 1.0
        assert instance.debt_rate > 0.0
        assert instance.return_on_equity > 0.0
        assert 0.0 <= instance.tax_rate <= 1.0


def test_no_warnings_building_a_capital_cost_curve_or_financial_data():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for tech_class in POWER_SYSTEMS_TYPE_BY_CLASS:
            capital_cost_curve(tech_class).model_dump(mode="json")
            financial_data_for(tech_class).model_dump(mode="json")


def test_flat_linear_value_curve_shape():
    curve = flat_linear_value_curve(123.0)
    dumped = curve.model_dump(mode="json")
    assert dumped["curve_type"] == "INPUT_OUTPUT"
    assert dumped["function_data"]["function_type"] == "LINEAR"
    assert dumped["function_data"]["constant_term"] == 0.0
    assert dumped["function_data"]["proportional_term"] == 123.0


def test_capital_cost_curve_is_built_from_flat_linear_value_curve():
    # capital_cost_curve is now a thin wrapper -- confirm it still produces
    # the same shape as before the E3 refactor.
    for tech_class, expected_cost in CAPITAL_COST_PER_MW.items():
        assert capital_cost_curve(tech_class).model_dump(
            mode="json"
        ) == flat_linear_value_curve(expected_cost).model_dump(mode="json")


def test_battery_capital_costs_are_positive_and_plausible_4hr_battery_scale():
    # Sanity check the E3 battery figures reconstruct to a plausible
    # ~$/kW total installed cost for a 4-hour duration (charge + discharge
    # legs plus 4 hours of energy-capacity cost), same order of magnitude
    # as NREL ATB's ~$1,590/kW 2030-moderate 4-hour utility battery figure.
    assert BATTERY_CAPITAL_COST_PER_MW_CHARGE > 0
    assert BATTERY_CAPITAL_COST_PER_MW_DISCHARGE > 0
    assert BATTERY_CAPITAL_COST_PER_MWH_ENERGY > 0

    total_per_mw = (
        BATTERY_CAPITAL_COST_PER_MW_CHARGE
        + BATTERY_CAPITAL_COST_PER_MW_DISCHARGE
        + 4 * BATTERY_CAPITAL_COST_PER_MWH_ENERGY
    )
    assert 5e5 < total_per_mw < 3e6, f"{total_per_mw}: out of plausible USD/MW range"

    costs = battery_capital_costs()
    # The three legs travel in one StorageCapitalCost, which also carries
    # interconnection_cost (left at its schema default).
    assert costs.interconnection_cost == 0.0
    for curve, expected in (
        (costs.charge_capital_cost, BATTERY_CAPITAL_COST_PER_MW_CHARGE),
        (costs.discharge_capital_cost, BATTERY_CAPITAL_COST_PER_MW_DISCHARGE),
        (costs.energy_capital_cost, BATTERY_CAPITAL_COST_PER_MWH_ENERGY),
    ):
        dumped = curve.model_dump(mode="json")
        assert dumped["function_data"]["proportional_term"] == expected


def test_battery_operation_cost_is_zero_and_fully_populated():
    cost = battery_operation_cost()
    assert cost.cost_type == "STORAGE"
    assert cost.fixed == 0.0
    assert cost.shut_down == 0.0
    assert cost.start_up == 0.0
    assert cost.energy_shortage_cost == 0.0
    assert cost.energy_surplus_cost == 0.0


def test_transport_financial_data_has_the_sourced_capital_recovery_period():
    instances = [transport_financial_data() for _ in range(3)]
    # A fresh instance per call, like financial_data_for.
    assert len({id(instance) for instance in instances}) == 3

    for instance in instances:
        assert instance.capital_recovery_period == 40
        assert isinstance(instance.technology_base_year, int)
        assert 0.0 <= instance.debt_fraction <= 1.0
        assert instance.debt_rate > 0.0
        assert instance.return_on_equity > 0.0
        assert 0.0 <= instance.tax_rate <= 1.0


def test_no_warnings_building_storage_and_transport_cost_helpers():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        battery_capital_costs().model_dump(mode="json")
        battery_operation_cost().model_dump(mode="json")
        transport_financial_data().model_dump(mode="json")
