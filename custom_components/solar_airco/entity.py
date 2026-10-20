"""Shared entity base."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AircoSettings, SolarAircoCoordinator
from .logic import Decision


class SolarAircoEntity(CoordinatorEntity[SolarAircoCoordinator]):
    """Entity of the main device (subentry_id None) or of one airco."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarAircoCoordinator,
        key: str,
        subentry_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.subentry_id = subentry_id
        self._attr_translation_key = key
        scope = subentry_id or entry.entry_id
        self._attr_unique_id = f"{scope}_{key}"
        title = entry.subentries[subentry_id].title if subentry_id else entry.title
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, scope)},
            name=title,
            manufacturer="Solar Airco",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def settings(self) -> AircoSettings:
        assert self.subentry_id is not None
        return self.coordinator.settings[self.subentry_id]

    @property
    def decision(self) -> Decision | None:
        if self.subentry_id is None or self.coordinator.data is None:
            return None
        return self.coordinator.data.decisions.get(self.subentry_id)
