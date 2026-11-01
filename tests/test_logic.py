import importlib.util
import os
import sys
import unittest
from datetime import datetime, time, timedelta, timezone

_path = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "solar_airco", "logic.py"
)
_spec = importlib.util.spec_from_file_location("solar_airco_logic", _path)
logic = importlib.util.module_from_spec(_spec)
sys.modules["solar_airco_logic"] = logic
_spec.loader.exec_module(logic)

AircoSpec = logic.AircoSpec
AircoState = logic.AircoState
DECISION_MODES = logic.DECISION_MODES
in_day_period = logic.in_day_period
plan = logic.plan

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def spec(**kwargs):
    values = {
        "name": "living_room",
        "entity": "climate.living_room",
        "min_temp": 18.0,
        "desired_temp": 21.0,
        "night_temp": 17.0,
        "day_start": time(8),
        "day_end": time(21),
        "priority": 1,
    }
    values.update(kwargs)
    values["entity"] = kwargs.get("entity", f"climate.{values['name']}")
    return AircoSpec(**values)


def decision(current_setpoint, balance, **airco_options):
    airco = spec(**airco_options)
    decisions, info = plan(
        NOW,
        [airco],
        {"living_room": AircoState("heat", current_setpoint)},
        balance,
    )
    return decisions[0], info


class AircoLogicTests(unittest.TestCase):
    def test_decision_modes_include_every_sensor_state(self):
        self.assertEqual(
            set(DECISION_MODES),
            {"solar", "consuming", "balanced", "night", "hold", "unmanaged"},
        )

    def test_solar_surplus_increases_setpoint_by_one_degree(self):
        result, info = decision(19.0, 1200)
        self.assertEqual((result.action, result.mode, result.setpoint), ("set", "solar", 20.0))
        self.assertEqual(info["solar_balance_w"], 1200)

    def test_setpoint_stops_at_desired_temperature(self):
        result, _ = decision(20.5, 1200)
        self.assertEqual(result.setpoint, 21.0)

    def test_consumption_decreases_setpoint_by_one_degree(self):
        result, _ = decision(20.0, -100)
        self.assertEqual((result.mode, result.setpoint), ("consuming", 19.0))

    def run_plan(self, aircos, setpoints, balance, **kwargs):
        states = {a.name: AircoState("heat", setpoints[a.name]) for a in aircos}
        return {d.name: d for d in plan(NOW, aircos, states, balance, **kwargs)[0]}

    def changed(self, result):
        return [name for name, d in result.items() if d.action == "set"]

    def test_only_one_airco_changes_per_update(self):
        aircos = [spec(name="a"), spec(name="b"), spec(name="c")]
        result = self.run_plan(aircos, {"a": 19.0, "b": 19.0, "c": 19.0}, 500)
        self.assertEqual(self.changed(result), ["a"])
        result = self.run_plan(aircos, {"a": 20.0, "b": 20.0, "c": 20.0}, -500)
        self.assertEqual(self.changed(result), ["a"])

    def test_increase_lowest_delta_first(self):
        aircos = [spec(name="a"), spec(name="b")]
        result = self.run_plan(aircos, {"a": 20.0, "b": 19.0}, 500)
        self.assertEqual(self.changed(result), ["b"])
        self.assertEqual(result["b"].setpoint, 20.0)

    def test_decrease_highest_delta_first(self):
        aircos = [spec(name="a"), spec(name="b")]
        result = self.run_plan(aircos, {"a": 19.0, "b": 21.0}, -500)
        self.assertEqual(self.changed(result), ["b"])
        self.assertEqual(result["b"].setpoint, 20.0)

    def test_equal_delta_uses_priority(self):
        aircos = [spec(name="a", priority=2), spec(name="b", priority=1)]
        setpoints = {"a": 19.0, "b": 19.0}
        self.assertEqual(self.changed(self.run_plan(aircos, setpoints, 500)), ["b"])
        self.assertEqual(self.changed(self.run_plan(aircos, setpoints, -500)), ["a"])

    def test_equal_delta_and_priority_uses_list_order(self):
        aircos = [spec(name="a"), spec(name="b")]
        setpoints = {"a": 19.0, "b": 19.0}
        self.assertEqual(self.changed(self.run_plan(aircos, setpoints, 500)), ["a"])
        self.assertEqual(self.changed(self.run_plan(aircos, setpoints, -500)), ["a"])

    def test_full_airco_is_skipped_when_increasing(self):
        aircos = [spec(name="a"), spec(name="b")]
        result = self.run_plan(aircos, {"a": 21.0, "b": 19.0}, 500)
        self.assertEqual(self.changed(result), ["b"])

    def test_increase_needs_surplus_above_threshold(self):
        result = self.run_plan([spec()], {"living_room": 19.0}, 300, increase_threshold_w=300)
        self.assertEqual(self.changed(result), [])
        result = self.run_plan([spec()], {"living_room": 19.0}, 301, increase_threshold_w=300)
        self.assertEqual(self.changed(result), ["living_room"])

    def test_decrease_needs_consumption_above_threshold(self):
        result = self.run_plan([spec()], {"living_room": 20.0}, -200, decrease_threshold_w=200)
        self.assertEqual(self.changed(result), [])
        result = self.run_plan([spec()], {"living_room": 20.0}, -201, decrease_threshold_w=200)
        self.assertEqual(self.changed(result), ["living_room"])

    def test_decrease_locked_after_increase(self):
        aircos = [spec(name="a"), spec(name="b")]
        setpoints = {"a": 21.0, "b": 20.0}
        last = {"a": NOW - timedelta(minutes=5)}
        result = self.run_plan(
            aircos, setpoints, -500, decrease_lock_minutes=10, last_increase=last
        )
        self.assertEqual(self.changed(result), ["b"])
        last = {"a": NOW - timedelta(minutes=11)}
        result = self.run_plan(
            aircos, setpoints, -500, decrease_lock_minutes=10, last_increase=last
        )
        self.assertEqual(self.changed(result), ["a"])

    def test_consumption_never_decreases_below_minimum(self):
        result, _ = decision(18.0, -100)
        self.assertEqual((result.action, result.setpoint), ("none", 18.0))

    def test_zero_balance_keeps_setpoint(self):
        result, _ = decision(19.5, 0)
        self.assertEqual((result.action, result.mode, result.setpoint), ("none", "balanced", 19.5))

    def test_missing_solar_data_keeps_current_setpoint(self):
        result, info = decision(19.5, None)
        self.assertEqual((result.action, result.mode, result.setpoint), ("none", "hold", 19.5))
        self.assertIsNone(info["solar_balance_w"])

    def test_missing_setpoint_starts_at_minimum_and_uses_solar(self):
        result, _ = decision(None, 100)
        self.assertEqual(result.setpoint, 19.0)

    def test_night_period_applies_fixed_temperature(self):
        result, _ = decision(20.0, 1000, day_start=time(19), day_end=time(7))
        self.assertEqual((result.mode, result.setpoint), ("night", 17.0))

    def test_day_period_can_cross_midnight(self):
        airco = spec(day_start=time(22), day_end=time(6))
        self.assertTrue(in_day_period(airco, NOW.replace(hour=23)))
        self.assertFalse(in_day_period(airco, NOW))

    def test_off_airco_is_set_to_heat_mode(self):
        airco = spec()
        decisions, _ = plan(
            NOW,
            [airco],
            {"living_room": AircoState("off", 20.0)},
            100,
        )
        self.assertEqual(decisions[0].action, "set")

    def test_missing_solar_data_does_not_turn_on_airco(self):
        airco = spec()
        decisions, _ = plan(
            NOW,
            [airco],
            {"living_room": AircoState("off", None)},
            None,
        )
        self.assertEqual((decisions[0].action, decisions[0].mode), ("none", "hold"))

    def test_other_modes_are_left_alone(self):
        airco = spec()
        decisions, _ = plan(
            NOW,
            [airco],
            {"living_room": AircoState("cool", 19.0)},
            1000,
        )
        self.assertEqual((decisions[0].action, decisions[0].mode), ("none", "unmanaged"))


if __name__ == "__main__":
    unittest.main()
