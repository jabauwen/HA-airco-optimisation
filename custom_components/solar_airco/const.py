"""Constants for Solar Airco."""
from __future__ import annotations

DOMAIN = "solar_airco"

SUBENTRY_AIRCO = "airco"

CONF_PV_POWER = "pv_power_entity"
CONF_BASE_LOAD = "base_load_entity"
CONF_FALLBACK_BASE_LOAD = "fallback_base_load_w"
CONF_FORECAST_ENTITIES = "forecast_entities"
CONF_FORECAST_FIELD = "forecast_field"
CONF_FORECAST_WEIGHT = "forecast_weight"

CONF_AIRCO_NAME = "name"
CONF_CLIMATE = "climate_entity"
CONF_POWER_MAX = "power_max"
CONF_POWER_IDLE = "power_idle"

DEFAULT_FALLBACK_BASE_LOAD = 400
DEFAULT_FORECAST_FIELD = "pv_estimate"
DEFAULT_FORECAST_WEIGHT = 0.5
DEFAULT_POWER_MAX = 900
DEFAULT_POWER_IDLE = 50

FORECAST_FIELDS = ["pv_estimate", "pv_estimate10", "pv_estimate90"]
UPDATE_INTERVAL_S = 60
