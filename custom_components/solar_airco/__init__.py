"""Solar Airco: solar-aware heating control for air conditioners."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_CLIMATE
from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH, Platform.TIME]


async def async_setup_entry(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> bool:
    coordinator = SolarAircoCoordinator(hass, entry)
    entry.runtime_data = coordinator

    # Entities restore their last values while being added, so plan only after that
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()

    @callback
    def _climate_changed(event: Event) -> None:
        hass.async_create_task(coordinator.async_request_refresh())

    climates = [sub.data[CONF_CLIMATE] for sub in entry.subentries.values()]
    if climates:
        entry.async_on_unload(async_track_state_change_event(hass, climates, _climate_changed))
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))
    return True


async def _reload_on_update(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SolarAircoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
