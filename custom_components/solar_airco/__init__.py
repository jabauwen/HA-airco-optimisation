"""Solar Airco: solar-aware heating control for air conditioners."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH, Platform.TIME]


async def async_setup_entry(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> bool:
    coordinator = SolarAircoCoordinator(hass, entry)
    entry.runtime_data = coordinator

    # Entities restore their last values while being added, so plan only after that
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))
    return True


async def _reload_on_update(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
