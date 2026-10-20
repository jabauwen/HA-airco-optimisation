"""Number entities: minimum / desired temperature and priority per airco."""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator
from .entity import SolarAircoEntity

# key -> (min, max, step, mode, unit, icon)
NUMBERS = {
    "min_temp": (10, 25, 0.5, NumberMode.BOX, UnitOfTemperature.CELSIUS, "mdi:thermometer-low"),
    "desired_temp": (10, 26, 0.5, NumberMode.BOX, UnitOfTemperature.CELSIUS, "mdi:thermometer"),
    "priority": (1, 10, 1, NumberMode.BOX, None, "mdi:sort-numeric-ascending"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarAircoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    for sid in entry.subentries:
        async_add_entities(
            [SettingNumber(coordinator, key, sid) for key in NUMBERS], config_subentry_id=sid
        )


class SettingNumber(SolarAircoEntity, RestoreNumber):
    def __init__(self, coordinator: SolarAircoCoordinator, key: str, subentry_id: str) -> None:
        super().__init__(coordinator, key, subentry_id)
        self._key = key
        low, high, step, mode, unit, icon = NUMBERS[key]
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_mode = mode
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def native_value(self) -> float:
        return float(getattr(self.settings, self._key))

    def _store(self, value: float) -> None:
        setattr(self.settings, self._key, int(value) if self._key == "priority" else float(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._store(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._store(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
