"""Sensors: estimated power, mode and the solar numbers behind the decisions."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SolarAircoConfigEntry, SolarAircoCoordinator
from .entity import SolarAircoEntity

MODES = ["solar", "comfort", "off", "hold", "unmanaged"]
STATUSES = ["active", "dry_run", "disabled"]


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarAircoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            StatusSensor(coordinator),
            TotalPowerSensor(coordinator),
            InfoSensor(coordinator, "pv_effective", "pv_effective_w"),
            InfoSensor(coordinator, "surplus", "surplus_w"),
        ]
    )
    for sid in entry.subentries:
        async_add_entities(
            [AircoPowerSensor(coordinator, sid), AircoModeSensor(coordinator, sid)], config_subentry_id=sid
        )


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


class TotalPowerSensor(_PowerSensor):
    """Estimated power of all airco's that heat after the latest decision."""

    def __init__(self, coordinator: SolarAircoCoordinator) -> None:
        super().__init__(coordinator, "total_power")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None or data.status == "disabled":
            return None
        return sum(d.est_power_w for d in data.decisions.values() if d.heating)


class InfoSensor(_PowerSensor):
    def __init__(self, coordinator: SolarAircoCoordinator, key: str, info_key: str) -> None:
        super().__init__(coordinator, key)
        self._info_key = info_key

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.info.get(self._info_key) if data else None


class AircoPowerSensor(_PowerSensor):
    def __init__(self, coordinator: SolarAircoCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, "airco_power", subentry_id)

    @property
    def native_value(self) -> float | None:
        decision = self.decision
        if decision is None:
            return None
        return decision.est_power_w if decision.heating else 0


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
