"""Diagnostics : export de l'état de l'intégration, sans données personnelles."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import YokisConfigEntry

# L'email sert aussi de titre et d'identifiant unique de l'entrée.
TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "title", "unique_id", "mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: YokisConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "gateway_online": coordinator.gateway_online,
        },
        "equipments": async_redact_data(coordinator.data, TO_REDACT),
    }
