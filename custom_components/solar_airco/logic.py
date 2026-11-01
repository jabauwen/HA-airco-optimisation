"""Setpoint decisions for the solar airco controller.

Pure Python without Home Assistant imports, so it can be unit tested outside HA.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Tuple

MANAGED_MODES = ("off", "heat")
DECISION_MODES = ("solar", "consuming", "balanced", "night", "hold", "unmanaged")


@dataclass
class AircoSpec:
    name: str
    entity: str
    min_temp: float
    desired_temp: float
    night_temp: float
    day_start: time
    day_end: time
    priority: int = 1


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
    increase_threshold_w: float = 0.0,
    decrease_threshold_w: float = 0.0,
    decrease_lock_minutes: float = 0.0,
    last_increase: Optional[dict[str, datetime]] = None,
) -> Tuple[list[Decision], dict[str, Optional[float]]]:
    """Plan setpoints; at most one day-time airco is adjusted per call.

    Increase (balance above increase_threshold_w): the airco with the lowest
    delta (setpoint - minimum) goes first. Decrease (grid consumption above
    decrease_threshold_w): the highest delta goes first; aircos increased less
    than decrease_lock_minutes ago are skipped. Ties are resolved by priority
    (1 first when increasing, highest number first when decreasing), then by
    list order.
    """
    last_increase = last_increase or {}
    decisions: list[Decision] = []
    # (decision index, spec, current setpoint) of managed aircos in their day period
    day_aircos: list[tuple[int, AircoSpec, float]] = []

    if solar_balance_w is None:
        day_mode, day_reason = "hold", "solar balance unavailable"
    elif solar_balance_w > increase_threshold_w:
        day_mode, day_reason = "solar", "waiting for aircos with a lower temperature delta"
    elif solar_balance_w < -decrease_threshold_w:
        day_mode, day_reason = "consuming", "waiting for aircos with a higher temperature delta"
    else:
        day_mode, day_reason = "balanced", "solar balance within thresholds"

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

        if not in_day_period(spec, now):
            changed = state.setpoint is None or abs(state.setpoint - spec.night_temp) >= 0.25
            action = "set" if changed or state.hvac_mode == "off" else "none"
            decisions.append(
                Decision(
                    spec.name, spec.entity, action, "night", spec.night_temp, "night temperature"
                )
            )
            continue

        current = state.setpoint if state.setpoint is not None else spec.min_temp
        current = max(spec.min_temp, min(max(spec.min_temp, spec.desired_temp), current))
        shown = state.setpoint if state.setpoint is not None else current
        day_aircos.append((len(decisions), spec, current))
        decisions.append(
            Decision(spec.name, spec.entity, "none", day_mode, shown, day_reason)
        )

    if day_mode in ("solar", "consuming"):
        candidates = []
        for order, (index, spec, current) in enumerate(day_aircos):
            delta = current - spec.min_temp
            if day_mode == "solar":
                if current < max(spec.min_temp, spec.desired_temp):
                    candidates.append(((delta, spec.priority, order), index, spec, current))
            elif current > spec.min_temp:
                locked_at = last_increase.get(spec.name)
                if (
                    locked_at is not None
                    and (now - locked_at).total_seconds() < decrease_lock_minutes * 60
                ):
                    decisions[index].reason = (
                        "temperature was increased recently; decrease locked"
                    )
                    continue
                candidates.append(((-delta, -spec.priority, order), index, spec, current))
        if candidates:
            _, index, spec, current = min(candidates, key=lambda item: item[0])
            delta = current - spec.min_temp
            others = ", ".join(
                f"{item[2].name} (delta {item[3] - item[2].min_temp:g}, priority {item[2].priority})"
                for item in candidates
                if item[1] != index
            ) or "none"
            if day_mode == "solar":
                target = min(max(spec.min_temp, spec.desired_temp), current + 1)
                reason = (
                    f"solar surplus {solar_balance_w:g} W > {increase_threshold_w:g} W: "
                    f"increase {current:g} -> {target:g} °C; lowest delta {delta:g} °C "
                    f"(priority {spec.priority}); other candidates: {others}"
                )
            else:
                target = max(spec.min_temp, current - 1)
                reason = (
                    f"grid consumption {-solar_balance_w:g} W > {decrease_threshold_w:g} W: "
                    f"decrease {current:g} -> {target:g} °C; highest delta {delta:g} °C "
                    f"(priority {spec.priority}); other candidates: {others}"
                )
            decisions[index] = Decision(
                spec.name, spec.entity, "set", day_mode, target, reason
            )

    return decisions, {"solar_balance_w": solar_balance_w}
