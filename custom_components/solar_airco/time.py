"""Time entities: start and end of the heating window per airco."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator
from .entity import SolarAircoEntity

KEYS = {"start": "mdi:clock-start", "end": "mdi:clock-end"}


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarAircoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    for sid in entry.subentries:
        async_add_entities([WindowTime(coordinator, key, sid) for key in KEYS], config_subentry_id=sid)


class WindowTime(SolarAircoEntity, TimeEntity, RestoreEntity):
    def __init__(self, coordinator: SolarAircoCoordinator, key: str, subentry_id: str) -> None:
        super().__init__(coordinator, key, subentry_id)
        self._key = key
        self._attr_icon = KEYS[key]

    @property
    def native_value(self) -> time:
        return getattr(self.settings, self._key)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            try:
                setattr(self.settings, self._key, time.fromisoformat(last.state))
            except ValueError:
                pass

    async def async_set_value(self, value: time) -> None:
        setattr(self.settings, self._key, value.replace(microsecond=0))
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
