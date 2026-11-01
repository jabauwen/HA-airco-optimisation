"""Coordinator: measures solar balance and applies thermostat setpoints."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_LOAD,
    CONF_CLIMATE,
    CONF_DECREASE_LOCK_MINUTES,
    CONF_DECREASE_THRESHOLD,
    CONF_FALLBACK_BASE_LOAD,
    CONF_INCREASE_THRESHOLD,
    CONF_PV_POWER,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_DECREASE_LOCK_MINUTES,
    DEFAULT_DECREASE_THRESHOLD,
    DEFAULT_FALLBACK_BASE_LOAD,
    DEFAULT_INCREASE_THRESHOLD,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from .logic import AircoSpec, AircoState, Decision, plan, to_float

_LOGGER = logging.getLogger(__name__)

type SolarAircoConfigEntry = ConfigEntry[SolarAircoCoordinator]


@dataclass
class AircoSettings:
    """User settings of one airco, exposed as entities."""

    min_temp: float = 18.0
    desired_temp: float = 21.0
    night_temp: float = 17.0
    day_start: time = time(8, 0)
    day_end: time = time(21, 0)
    priority: int = 1
    enabled: bool = True


@dataclass
class PlanData:
    status: str
    decisions: dict[str, Decision] = field(default_factory=dict)
    info: dict[str, float | None] = field(default_factory=dict)


class SolarAircoCoordinator(DataUpdateCoordinator[PlanData]):
    """Evaluates all aircos at the configured interval."""

    config_entry: SolarAircoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SolarAircoConfigEntry) -> None:
        config = {**entry.data, **entry.options}
        interval = int(
            config.get(CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=interval),
        )
        self.enabled = True
        self.dry_run = True
        self.last_increase: dict[str, datetime] = {}
        self.settings: dict[str, AircoSettings] = {
            sid: AircoSettings() for sid in entry.subentries
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
        pv = to_float(self._state_value(cfg.get(CONF_PV_POWER)))
        base_load = to_float(self._state_value(cfg.get(CONF_BASE_LOAD)))
        if base_load is None:
            base_load = float(
                cfg.get(CONF_FALLBACK_BASE_LOAD, DEFAULT_FALLBACK_BASE_LOAD)
            )
        solar_balance = pv - base_load if pv is not None else None

        now = dt_util.now()
        specs: list[AircoSpec] = []
        states: dict[str, AircoState] = {}
        decisions: dict[str, Decision] = {}
        for sid, subentry in self.config_entry.subentries.items():
            settings = self.settings[sid]
            entity_id = subentry.data[CONF_CLIMATE]
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                reason = "disabled" if not settings.enabled else "airco unavailable"
                decisions[sid] = Decision(
                    sid, entity_id, "none", "unmanaged", None, reason
                )
                continue
            if not settings.enabled:
                decisions[sid] = Decision(
                    sid, entity_id, "none", "unmanaged", None, "disabled"
                )
                continue

            specs.append(
                AircoSpec(
                    name=sid,
                    entity=entity_id,
                    min_temp=settings.min_temp,
                    desired_temp=settings.desired_temp,
                    night_temp=settings.night_temp,
                    day_start=settings.day_start,
                    day_end=settings.day_end,
                    priority=settings.priority,
                )
            )
            states[sid] = AircoState(
                hvac_mode=state.state,
                setpoint=to_float(state.attributes.get("temperature")),
            )

        planned, info = plan(
            now,
            specs,
            states,
            solar_balance,
            float(cfg.get(CONF_INCREASE_THRESHOLD, DEFAULT_INCREASE_THRESHOLD)),
            float(cfg.get(CONF_DECREASE_THRESHOLD, DEFAULT_DECREASE_THRESHOLD)),
            float(cfg.get(CONF_DECREASE_LOCK_MINUTES, DEFAULT_DECREASE_LOCK_MINUTES)),
            self.last_increase,
        )
        for decision in planned:
            if decision.action == "set":
                spec_state = states.get(decision.name)
                _LOGGER.info(
                    "%s %s (%s): setpoint %s -> %s [%s mode; pv=%s W, consumption=%s W, "
                    "balance=%s W]: %s",
                    "Would update" if self.dry_run else "Updating",
                    decision.name,
                    decision.entity,
                    spec_state.setpoint if spec_state else None,
                    decision.setpoint,
                    decision.mode,
                    pv,
                    base_load,
                    solar_balance,
                    decision.reason,
                )
            decisions[decision.name] = decision
            if decision.mode == "solar" and decision.action == "set":
                self.last_increase[decision.name] = now
            if not self.dry_run:
                await self._apply(decision)

        status = "dry_run" if self.dry_run else "active"
        return PlanData(status=status, decisions=decisions, info=info)

    async def _call(self, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call("climate", service, data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "climate.%s failed for %s: %s",
                service,
                data.get(ATTR_ENTITY_ID),
                err,
            )

    async def _apply(self, decision: Decision) -> None:
        if decision.action != "set" or decision.setpoint is None:
            return

        state = self.hass.states.get(decision.entity)
        if state is None or state.state not in ("off", "heat"):
            return
        if state.state == "off":
            await self._call(
                "set_hvac_mode",
                {ATTR_ENTITY_ID: decision.entity, "hvac_mode": "heat"},
            )

        low = to_float(state.attributes.get("min_temp"))
        high = to_float(state.attributes.get("max_temp"))
        target = max(low or 10.0, min(high or 31.0, decision.setpoint))
        current = to_float(state.attributes.get("temperature"))
        if current is None or abs(current - target) >= 0.25:
            await self._call(
                "set_temperature",
                {ATTR_ENTITY_ID: decision.entity, "temperature": target},
            )
