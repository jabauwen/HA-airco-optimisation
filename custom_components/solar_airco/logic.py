"""Planning logic for the airco heating controller.

Pure Python without Home Assistant imports, so it can be unit tested outside HA.
The coordinator reads the states, calls plan() and applies the result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

MANAGED_MODES = ("off", "heat")
FORECAST_STEP = timedelta(minutes=30)

Forecast = List[Tuple[datetime, float]]


@dataclass
class AircoSpec:
    name: str
    entity: str
    min_temp: float
    desired_temp: float
    start: time
    end: time
    power_max: float = 900.0
    power_idle: float = 50.0
    # Temperature gap (degrees below desired) at which the unit draws its full power
    ramp: float = 3.0
    # Lower number = gets the solar surplus first
    priority: int = 100


@dataclass
class AircoState:
    hvac_mode: str
    temp: Optional[float]
    setpoint: Optional[float] = None
    last_change: Optional[datetime] = None


@dataclass
class Tunables:
    # Share of the Solcast forecast (vs. the actual PV production) in the effective PV power
    forecast_weight: float = 0.5
    # Share of the estimated draw that must be available as surplus to start / keep heating on solar
    start_ratio: float = 0.6
    stop_ratio: float = 0.25
    hysteresis: float = 0.5
    # Degrees below min_temp at which we heat from the grid without waiting for solar
    urgent_margin: float = 1.0
    lookahead_min: int = 90
    min_on_s: int = 600
    min_off_s: int = 600


@dataclass
class Decision:
    name: str
    entity: str
    action: str  # "on", "off" or "none" (leave the unit as it is)
    mode: str  # "solar", "comfort", "off", "hold" or "unmanaged"
    setpoint: Optional[float]
    reason: str
    est_power_w: float
    heating: bool  # whether the unit is heating after this decision


def parse_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    parts = str(value).split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def to_float(value: Any) -> Optional[float]:
    if value is None or str(value).lower() in ("unknown", "unavailable", "none", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ceil_half(value: float) -> float:
    return math.ceil(value * 2) / 2


def in_window(spec: AircoSpec, moment: datetime) -> bool:
    t = moment.time()
    if spec.start == spec.end:
        return True
    if spec.start < spec.end:
        return spec.start <= t < spec.end
    return t >= spec.start or t < spec.end


def estimate_power(spec: AircoSpec, temp: float) -> float:
    """Expected draw while heating: falls towards idle as the room nears the desired temperature."""
    gap = spec.desired_temp - temp
    if gap <= 0:
        return spec.power_idle
    return spec.power_idle + (spec.power_max - spec.power_idle) * min(1.0, gap / spec.ramp)


def _to_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def parse_forecast(sources: Sequence[Any], field: str = "pv_estimate", factor: float = 1000.0) -> Forecast:
    """Merge Solcast `detailedForecast` lists (kW, 30 min periods) into sorted (start, watts) pairs."""
    merged: Dict[datetime, float] = {}
    for items in sources:
        for item in items or []:
            try:
                merged[_to_datetime(item["period_start"])] = float(item[field]) * factor
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(merged.items())


def average_forecast(forecast: Forecast, start: datetime, minutes: float) -> Optional[float]:
    end = start + timedelta(minutes=minutes)
    total = weight = 0.0
    for p_start, watts in forecast:
        overlap = (min(end, p_start + FORECAST_STEP) - max(start, p_start)).total_seconds()
        if overlap > 0:
            total += watts * overlap
            weight += overlap
    return total / weight if weight else None


def effective_pv(pv_actual: Optional[float], forecast: Forecast, now: datetime, tun: Tunables) -> float:
    predicted = average_forecast(forecast, now, FORECAST_STEP.total_seconds() / 60)
    if predicted is None:
        return max(pv_actual or 0.0, 0.0)
    if pv_actual is None:
        return predicted
    return tun.forecast_weight * predicted + (1 - tun.forecast_weight) * pv_actual


def solar_expected_soon(
    spec: AircoSpec, forecast: Forecast, now: datetime, base_load: float, needed_w: float, minutes: int
) -> bool:
    horizon = now + timedelta(minutes=minutes)
    for p_start, watts in forecast:
        if p_start + FORECAST_STEP <= now or p_start > horizon:
            continue
        if in_window(spec, max(p_start, now)) and watts - base_load >= needed_w:
            return True
    return False


def plan(
    now: datetime,
    specs: Sequence[AircoSpec],
    states: Dict[str, AircoState],
    pv_actual_w: Optional[float],
    base_load_w: float,
    forecast: Forecast,
    tun: Tunables,
) -> Tuple[List[Decision], Dict[str, float]]:
    pv_eff = effective_pv(pv_actual_w, forecast, now, tun)
    surplus = max(0.0, pv_eff - base_load_w)
    info = {"pv_effective_w": round(pv_eff), "surplus_w": round(surplus)}
    decisions: List[Decision] = []

    for spec in sorted(specs, key=lambda s: s.priority):
        st = states[spec.name]
        is_on = st.hvac_mode == "heat"

        def make(action, mode, reason, setpoint=None, est=0.0, heating=None):
            return Decision(
                spec.name, spec.entity, action, mode, setpoint, reason, round(est),
                is_on if heating is None else heating,
            )

        if st.hvac_mode not in MANAGED_MODES:
            decisions.append(make("none", "unmanaged", f"mode '{st.hvac_mode}' is not managed", heating=False))
            continue
        if st.temp is None:
            decisions.append(make("none", "hold", "no room temperature available"))
            continue

        est = estimate_power(spec, st.temp)
        if not in_window(spec, now):
            decisions.append(make("off" if is_on else "none", "off", "outside heating window", heating=False))
            continue

        hyst = tun.hysteresis
        want_on, mode, setpoint, reason = False, "off", None, "desired temperature reached"

        if st.temp < spec.desired_temp - (0 if is_on else hyst):
            needed = est * (tun.stop_ratio if is_on else tun.start_ratio)
            if surplus >= needed:
                want_on, mode, setpoint = True, "solar", spec.desired_temp
                reason = f"solar surplus {round(surplus)} W covers ~{round(est)} W"
                surplus = max(0.0, surplus - est)
            else:
                reason = "waiting for solar surplus"

        if not want_on and st.temp < spec.min_temp + (hyst if is_on else 0):
            urgent = st.temp < spec.min_temp - tun.urgent_margin
            if not is_on and not urgent and solar_expected_soon(
                spec, forecast, now, base_load_w, est * tun.start_ratio, tun.lookahead_min
            ):
                reason = "below minimum, but solar surplus expected soon"
            else:
                want_on, mode = True, "comfort"
                setpoint = ceil_half(spec.min_temp + hyst)
                reason = "keeping minimum temperature"

        if want_on != is_on and st.last_change is not None:
            elapsed = (now - st.last_change).total_seconds()
            limit = tun.min_off_s if want_on else tun.min_on_s
            if elapsed < limit:
                decisions.append(make("none", "hold", f"{'start' if want_on else 'stop'} delayed (min cycle time)"))
                continue

        if want_on:
            decisions.append(make("on", mode, reason, setpoint, est, True))
        else:
            decisions.append(make("off" if is_on else "none", "off", reason, heating=False))

    return decisions, info
