import importlib.util
import os
import sys
import unittest
from datetime import datetime, time, timezone

_path = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "solar_airco", "logic.py"
)
_spec = importlib.util.spec_from_file_location("solar_airco_logic", _path)
logic = importlib.util.module_from_spec(_spec)
sys.modules["solar_airco_logic"] = logic
_spec.loader.exec_module(logic)

AircoSpec = logic.AircoSpec
AircoState = logic.AircoState
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
    }
    values.update(kwargs)
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
            0,
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
