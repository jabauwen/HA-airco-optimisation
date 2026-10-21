"""Coordinator: reads the states, plans and (unless dry-run) switches the airco's."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_LOAD,
    CONF_BASE_LOAD_INCLUDES_AIRCOS,
    CONF_CLIMATE,
    CONF_FALLBACK_BASE_LOAD,
    CONF_FORECAST_ENTITIES,
    CONF_FORECAST_FIELD,
    CONF_FORECAST_WEIGHT,
    CONF_POWER_IDLE,
    CONF_POWER_MAX,
    CONF_PV_POWER,
    DEFAULT_FALLBACK_BASE_LOAD,
    DEFAULT_FORECAST_FIELD,
    DEFAULT_FORECAST_WEIGHT,
    DEFAULT_POWER_IDLE,
    DEFAULT_POWER_MAX,
    DOMAIN,
    UPDATE_INTERVAL_S,
)
from .logic import (
    AircoSpec,
    AircoState,
    Decision,
    Tunables,
    estimate_power,
    parse_forecast,
    plan,
    to_float,
)

_LOGGER = logging.getLogger(__name__)

type SolarAircoConfigEntry = ConfigEntry[SolarAircoCoordinator]


@dataclass
class AircoSettings:
    """User settings of one airco, exposed as entities."""

    min_temp: float = 18.0
    desired_temp: float = 21.0
    start: time = time(8, 0)
    end: time = time(21, 0)
    priority: int = 1
    enabled: bool = True


@dataclass
class PlanData:
    status: str
    decisions: dict[str, Decision] = field(default_factory=dict)
    info: dict[str, float] = field(default_factory=dict)


class SolarAircoCoordinator(DataUpdateCoordinator[PlanData]):
    """Evaluates all airco's every minute and on state changes."""

    config_entry: SolarAircoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SolarAircoConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self.enabled = True
        # Safe default: only report what would happen until the user turns dry-run off
        self.dry_run = True
        self.settings: dict[str, AircoSettings] = {
            sid: AircoSettings(priority=index + 1) for index, sid in enumerate(entry.subentries)
        }

    @property
    def config(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _state_value(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return None if state is None else state.state

    async def _async_update_data(self) -> PlanData:
        if not self.enabled:
            return PlanData(status="disabled")

        cfg = self.config
        now = dt_util.now()

        pv = to_float(self._state_value(cfg.get(CONF_PV_POWER)))
        base_load = to_float(self._state_value(cfg.get(CONF_BASE_LOAD)))
        base_load_includes_aircos = base_load is not None and cfg.get(
            CONF_BASE_LOAD_INCLUDES_AIRCOS, False
        )
        if base_load is None:
            base_load = float(cfg.get(CONF_FALLBACK_BASE_LOAD, DEFAULT_FALLBACK_BASE_LOAD))

        sources = []
        for entity_id in cfg.get(CONF_FORECAST_ENTITIES) or []:
            state = self.hass.states.get(entity_id)
            sources.append(state.attributes.get("detailedForecast") if state else None)
        forecast = parse_forecast(sources, cfg.get(CONF_FORECAST_FIELD, DEFAULT_FORECAST_FIELD))

        specs: list[AircoSpec] = []
        states: dict[str, AircoState] = {}
        decisions: dict[str, Decision] = {}
        estimated_current_airco_w = 0.0
        for sid, sub in self.config_entry.subentries.items():
            settings = self.settings[sid]
            entity_id = sub.data[CONF_CLIMATE]
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                reason = "disabled" if not settings.enabled else "airco unavailable"
                decisions[sid] = Decision(sid, entity_id, "none", "unmanaged", None, reason, 0, False)
                continue
            spec = AircoSpec(
                name=sid,
                entity=entity_id,
                min_temp=min(settings.min_temp, settings.desired_temp),
                desired_temp=settings.desired_temp,
                start=settings.start,
                end=settings.end,
                power_max=float(sub.data.get(CONF_POWER_MAX, DEFAULT_POWER_MAX)),
                power_idle=float(sub.data.get(CONF_POWER_IDLE, DEFAULT_POWER_IDLE)),
                priority=settings.priority,
            )
            airco_state = AircoState(
                hvac_mode=state.state,
                temp=to_float(state.attributes.get("current_temperature")),
                setpoint=to_float(state.attributes.get("temperature")),
                last_change=state.last_changed,
            )
            if base_load_includes_aircos and airco_state.hvac_mode == "heat" and airco_state.temp is not None:
                estimated_current_airco_w += estimate_power(spec, airco_state.temp)
            if not settings.enabled:
                decisions[sid] = Decision(sid, entity_id, "none", "unmanaged", None, "disabled", 0, False)
                continue
            specs.append(spec)
            states[sid] = airco_state

        tunables = Tunables(forecast_weight=float(cfg.get(CONF_FORECAST_WEIGHT, DEFAULT_FORECAST_WEIGHT)))
        planned, info = plan(
            now,
            specs,
            states,
            pv,
            base_load,
            forecast,
            tunables,
            base_load_includes_aircos,
            estimated_current_airco_w,
        )
        for decision in planned:
            decisions[decision.name] = decision
            if not self.dry_run:
                await self._apply(decision, states[decision.name])

        status = "dry_run" if self.dry_run else "active"
        return PlanData(status=status, decisions=decisions, info=info)

    async def _call(self, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call("climate", service, data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("climate.%s failed for %s: %s", service, data.get(ATTR_ENTITY_ID), err)

    async def _apply(self, decision: Decision, current: AircoState) -> None:
        if decision.action == "on":
            if current.hvac_mode != "heat":
                await self._call("set_hvac_mode", {ATTR_ENTITY_ID: decision.entity, "hvac_mode": "heat"})
            if decision.setpoint is not None:
                state = self.hass.states.get(decision.entity)
                low = to_float(state.attributes.get("min_temp")) if state else None
                high = to_float(state.attributes.get("max_temp")) if state else None
                target = max(low or 10.0, min(high or 31.0, decision.setpoint))
                if current.setpoint is None or abs(current.setpoint - target) >= 0.25:
                    await self._call("set_temperature", {ATTR_ENTITY_ID: decision.entity, "temperature": target})
        elif decision.action == "off" and current.hvac_mode == "heat":
            await self._call("set_hvac_mode", {ATTR_ENTITY_ID: decision.entity, "hvac_mode": "off"})
