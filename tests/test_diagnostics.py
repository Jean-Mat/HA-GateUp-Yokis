"""Tests de l'export des diagnostics."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yokis.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant

from .conftest import EMAIL, PASSWORD, UUID_BUREAU


async def test_diagnostics(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    setup_integration.runtime_data.data[UUID_BUREAU]["informations"]["mac"] = "00:11:22:33:44:55:66:77"

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    # Aucune donnée personnelle, où qu'elle soit dans l'export.
    dumped = json.dumps(diagnostics)
    for secret in (EMAIL, EMAIL.lower(), PASSWORD, "00:11:22:33:44:55:66:77"):
        assert secret not in dumped

    assert diagnostics["entry"]["data"] == {"email": REDACTED, "password": REDACTED}
    assert diagnostics["entry"]["title"] == REDACTED
    assert diagnostics["coordinator"] == {"last_update_success": True, "gateway_online": True}

    bureau = diagnostics["equipments"][UUID_BUREAU]
    assert bureau["name"] == "Volets bureau"
    assert bureau["state"]["percentage"] == 100
    assert bureau["informations"]["mac"] == REDACTED
    assert bureau["informations"]["modelIdentifier"] == "MVR500E-UP"
