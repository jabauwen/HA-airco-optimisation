"""Constants for Solar Airco."""
from __future__ import annotations

DOMAIN = "solar_airco"

SUBENTRY_AIRCO = "airco"

CONF_PV_POWER = "pv_power_entity"
CONF_BASE_LOAD = "base_load_entity"
CONF_FALLBACK_BASE_LOAD = "fallback_base_load_w"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"

CONF_INCREASE_THRESHOLD = "increase_threshold_w"
CONF_DECREASE_THRESHOLD = "decrease_threshold_w"
CONF_DECREASE_LOCK_MINUTES = "decrease_lock_minutes"

CONF_AIRCO_NAME = "name"
CONF_CLIMATE = "climate_entity"

DEFAULT_FALLBACK_BASE_LOAD = 400
DEFAULT_UPDATE_INTERVAL_MINUTES = 1
DEFAULT_INCREASE_THRESHOLD = 100
DEFAULT_DECREASE_THRESHOLD = 100
DEFAULT_DECREASE_LOCK_MINUTES = 10
