"""Config flow: global settings, plus one subentry per airco."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AIRCO_NAME,
    CONF_BASE_LOAD,
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
    FORECAST_FIELDS,
    SUBENTRY_AIRCO,
)


def _sensor_selector(**kwargs: Any) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", **kwargs))


def _number_selector(low: float, high: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low, max=high, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _global_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_PV_POWER): _sensor_selector(device_class="power"),
            vol.Optional(CONF_BASE_LOAD): _sensor_selector(device_class="power"),
            vol.Required(CONF_FALLBACK_BASE_LOAD, default=DEFAULT_FALLBACK_BASE_LOAD): _number_selector(
                0, 10000, 10, "W"
            ),
            vol.Optional(CONF_FORECAST_ENTITIES): _sensor_selector(multiple=True),
            vol.Required(CONF_FORECAST_FIELD, default=DEFAULT_FORECAST_FIELD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=FORECAST_FIELDS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_FORECAST_FIELD,
                )
            ),
            vol.Required(CONF_FORECAST_WEIGHT, default=DEFAULT_FORECAST_WEIGHT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1, step=0.05, mode=selector.NumberSelectorMode.SLIDER
                )
            ),
        }
    )


def _airco_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_AIRCO_NAME): selector.TextSelector(),
            vol.Required(CONF_CLIMATE): selector.EntitySelector(selector.EntitySelectorConfig(domain="climate")),
            vol.Required(CONF_POWER_MAX, default=DEFAULT_POWER_MAX): _number_selector(100, 5000, 50, "W"),
            vol.Required(CONF_POWER_IDLE, default=DEFAULT_POWER_IDLE): _number_selector(0, 500, 5, "W"),
        }
    )


class SolarAircoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_AIRCO: AircoSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SolarAircoOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Solar Airco", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_global_schema())


class SolarAircoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_global_schema(), current),
        )


class AircoSubentryFlow(ConfigSubentryFlow):
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_AIRCO_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_airco_schema())

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input[CONF_AIRCO_NAME], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(_airco_schema(), subentry.data),
        )
