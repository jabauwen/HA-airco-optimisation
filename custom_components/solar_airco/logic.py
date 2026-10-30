"""Setpoint decisions for the solar airco controller.

Pure Python without Home Assistant imports, so it can be unit tested outside HA.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Tuple

MANAGED_MODES = ("off", "heat")


@dataclass
class AircoSpec:
    name: str
    entity: str
    min_temp: float
    desired_temp: float
    night_temp: float
    day_start: time
    day_end: time


@dataclass
class AircoState:
    hvac_mode: str
    setpoint: Optional[float] = None


@dataclass
class Decision:
    name: str
    entity: str
    action: str
    mode: str
    setpoint: Optional[float]
    reason: str


def to_float(value: object) -> Optional[float]:
    if value is None or str(value).lower() in ("unknown", "unavailable", "none", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def in_day_period(spec: AircoSpec, moment: datetime) -> bool:
    current_time = moment.time()
    if spec.day_start == spec.day_end:
        return True
    if spec.day_start < spec.day_end:
        return spec.day_start <= current_time < spec.day_end
    return current_time >= spec.day_start or current_time < spec.day_end


def plan(
    now: datetime,
    specs: list[AircoSpec],
    states: dict[str, AircoState],
    solar_balance_w: Optional[float],
) -> Tuple[list[Decision], dict[str, Optional[float]]]:
    decisions: list[Decision] = []

    for spec in specs:
        state = states[spec.name]
        if state.hvac_mode not in MANAGED_MODES:
            decisions.append(
                Decision(
                    spec.name,
                    spec.entity,
                    "none",
                    "unmanaged",
                    None,
                    f"mode '{state.hvac_mode}' is not managed",
                )
            )
            continue

        minimum = spec.min_temp
        desired = max(minimum, spec.desired_temp)
        if not in_day_period(spec, now):
            target = spec.night_temp
            mode = "night"
            reason = "night temperature"
        elif solar_balance_w is None:
            target = state.setpoint if state.setpoint is not None else minimum
            mode = "hold"
            reason = "solar balance unavailable"
        else:
            current = state.setpoint if state.setpoint is not None else minimum
            current = max(minimum, min(desired, current))
            if solar_balance_w > 0:
                target = min(desired, current + 1)
                mode = "solar"
                reason = "solar energy available"
            elif solar_balance_w < 0:
                target = max(minimum, current - 1)
                mode = "consuming"
                reason = "consuming energy"
            else:
                target = current
                mode = "balanced"
                reason = "solar production matches consumption"

        changed = state.setpoint is None or abs(state.setpoint - target) >= 0.25
        needs_heat_mode = state.hvac_mode == "off" and mode != "hold"
        action = "set" if changed or needs_heat_mode else "none"
        if mode == "hold":
            action = "none"
        decisions.append(
            Decision(
                spec.name,
                spec.entity,
                action,
                mode,
                target,
                reason,
            )
        )

    return decisions, {"solar_balance_w": solar_balance_w}
