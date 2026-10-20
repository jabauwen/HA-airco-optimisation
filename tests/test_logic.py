import importlib.util
import os
import sys
import unittest
from datetime import datetime, time, timedelta, timezone

# Load logic.py by path: the package folder also contains a time.py platform that would shadow stdlib `time`
_path = os.path.join(os.path.dirname(__file__), "..", "custom_components", "solar_airco", "logic.py")
_spec = importlib.util.spec_from_file_location("solar_airco_logic", _path)
logic = importlib.util.module_from_spec(_spec)
sys.modules["solar_airco_logic"] = logic
_spec.loader.exec_module(logic)

AircoSpec = logic.AircoSpec
AircoState = logic.AircoState
Tunables = logic.Tunables
average_forecast = logic.average_forecast
estimate_power = logic.estimate_power
in_window = logic.in_window
parse_forecast = logic.parse_forecast
plan = logic.plan

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def spec(name="zit", priority=1, **kw):
    base = dict(
        name=name, entity=f"climate.{name}", min_temp=18, desired_temp=21,
        start=time(8), end=time(20), priority=priority,
    )
    base.update(kw)
    return AircoSpec(**base)


def forecast(*watts_per_half_hour, start=NOW):
    return [(start + timedelta(minutes=30 * i), w) for i, w in enumerate(watts_per_half_hour)]


def run(specs, states, pv=0.0, base=400.0, fc=None):
    decisions, info = plan(NOW, specs, states, pv, base, fc or [], Tunables())
    return {d.name: d for d in decisions}, info


class AircoLogicTests(unittest.TestCase):
    def test_outside_window_turns_off(self):
        s = spec(start=time(14), end=time(20))
        d, _ = run([s], {"zit": AircoState("heat", 19)})
        self.assertEqual(d["zit"].action, "off")

    def test_window_across_midnight(self):
        s = spec(start=time(22), end=time(6))
        self.assertTrue(in_window(s, NOW.replace(hour=23)))
        self.assertFalse(in_window(s, NOW))

    def test_solar_surplus_heats_to_desired(self):
        s = spec()
        d, _ = run([s], {"zit": AircoState("off", 19.5)}, pv=3000, fc=forecast(3000, 3000))
        self.assertEqual((d["zit"].action, d["zit"].mode, d["zit"].setpoint), ("on", "solar", 21))

    def test_no_solar_above_min_stays_off(self):
        d, _ = run([spec()], {"zit": AircoState("off", 19)})
        self.assertEqual(d["zit"].action, "none")

    def test_urgent_below_min_heats_from_grid(self):
        d, _ = run([spec()], {"zit": AircoState("off", 16.5)})
        self.assertEqual((d["zit"].action, d["zit"].mode, d["zit"].setpoint), ("on", "comfort", 18.5))

    def test_slightly_below_min_waits_for_coming_solar(self):
        d, _ = run([spec()], {"zit": AircoState("off", 17.5)}, fc=forecast(0, 0, 3000))
        self.assertEqual(d["zit"].action, "none")
        self.assertIn("expected soon", d["zit"].reason)

    def test_min_on_time_delays_stop(self):
        st = AircoState("heat", 19.5, last_change=NOW - timedelta(minutes=2))
        d, _ = run([spec()], {"zit": st})
        self.assertEqual(d["zit"].action, "none")
        self.assertTrue(d["zit"].heating)

    def test_stops_after_min_on_time(self):
        st = AircoState("heat", 19.5, last_change=NOW - timedelta(minutes=30))
        d, _ = run([spec()], {"zit": st})
        self.assertEqual(d["zit"].action, "off")

    def test_priority_shares_limited_surplus(self):
        specs = [spec("a", 1), spec("b", 2)]
        states = {"a": AircoState("off", 19), "b": AircoState("off", 19)}
        d, _ = run(specs, states, pv=1000)
        self.assertEqual((d["a"].action, d["b"].action), ("on", "none"))

    def test_other_modes_are_left_alone(self):
        d, _ = run([spec()], {"zit": AircoState("cool", 25)})
        self.assertEqual((d["zit"].action, d["zit"].mode), ("none", "unmanaged"))

    def test_power_drops_near_desired(self):
        s = spec()
        self.assertGreater(estimate_power(s, 18), estimate_power(s, 20.5))
        self.assertEqual(estimate_power(s, 21.5), s.power_idle)

    def test_forecast_parsing_and_average(self):
        raw = [{"period_start": NOW.isoformat(), "pv_estimate": 2.0},
               {"period_start": (NOW + timedelta(minutes=30)).isoformat(), "pv_estimate": 4.0}]
        fc = parse_forecast([raw, None])
        self.assertEqual([w for _, w in fc], [2000.0, 4000.0])
        self.assertAlmostEqual(average_forecast(fc, NOW, 60), 3000.0)




if __name__ == "__main__":
    unittest.main()
