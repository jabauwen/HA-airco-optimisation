"""Switches: master enable, dry-run and a per-airco enable."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator
from .entity import SolarAircoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarAircoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([ControllerSwitch(coordinator, "enabled"), ControllerSwitch(coordinator, "dry_run")])
    for sid in entry.subentries:
        async_add_entities([AircoEnabledSwitch(coordinator, sid)], config_subentry_id=sid)


class _RestoredSwitch(SolarAircoEntity, SwitchEntity, RestoreEntity):
    def _get(self) -> bool:
        raise NotImplementedError

    def _set(self, value: bool) -> None:
        raise NotImplementedError

    @property
    def is_on(self) -> bool:
        return self._get()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._set(last.state == "on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._change(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._change(False)

    async def _change(self, value: bool) -> None:
        self._set(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class ControllerSwitch(_RestoredSwitch):
    """Global switches: `enabled` (master) and `dry_run` (only report, never switch)."""

    def __init__(self, coordinator: SolarAircoCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._attr_icon = "mdi:radiator" if key == "enabled" else "mdi:test-tube"

    def _get(self) -> bool:
        return getattr(self.coordinator, self._key)

    def _set(self, value: bool) -> None:
        setattr(self.coordinator, self._key, value)


class AircoEnabledSwitch(_RestoredSwitch):
    def __init__(self, coordinator: SolarAircoCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, "airco_enabled", subentry_id)
        self._attr_icon = "mdi:air-conditioner"

    def _get(self) -> bool:
        return self.settings.enabled

    def _set(self, value: bool) -> None:
        self.settings.enabled = value
