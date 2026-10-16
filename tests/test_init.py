"""Tests du chargement / déchargement de l'intégration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yokis.api import YokisApiError, YokisAuthError
from custom_components.yokis.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import FakeNotifs


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_notifs: FakeNotifs
) -> None:
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data
    # Le flux SSE est ouvert dès le démarrage.
    assert fake_notifs.connections == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_auth_error_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_login.side_effect = YokisAuthError("refusé")

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.parametrize("failing_call", ["async_login", "async_get_equipments"])
async def test_setup_api_error_retries_later(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: MagicMock, failing_call: str
) -> None:
    getattr(mock_api, failing_call).side_effect = YokisApiError("réseau")

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Erreur passagère : Home Assistant retentera le chargement plus tard.
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
