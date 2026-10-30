"""Sensors for the measured solar balance and controller decisions."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator
from .entity import SolarAircoEntity
from .logic import DECISION_MODES

MODES = list(DECISION_MODES)
STATUSES = ["active", "dry_run", "disabled"]


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarAircoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            StatusSensor(coordinator),
            SolarBalanceSensor(coordinator),
        ]
    )
    for sid in entry.subentries:
        async_add_entities([AircoModeSensor(coordinator, sid)], config_subentry_id=sid)


class _PowerSensor(SolarAircoEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0


class StatusSensor(SolarAircoEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: SolarAircoCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.status if self.coordinator.data else None


class SolarBalanceSensor(_PowerSensor):
    def __init__(self, coordinator: SolarAircoCoordinator) -> None:
        super().__init__(coordinator, "solar_balance")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.info.get("solar_balance_w") if data else None


class AircoModeSensor(SolarAircoEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MODES
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: SolarAircoCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, "airco_mode", subentry_id)

    @property
    def native_value(self) -> str | None:
        decision = self.decision
        return decision.mode if decision else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        decision = self.decision
        if decision is None:
            return None
        return {"action": decision.action, "reason": decision.reason, "setpoint": decision.setpoint}
