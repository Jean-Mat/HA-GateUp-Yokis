"""Tests de l'écran de configuration (ajout du compte et ré-authentification)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yokis.api import YokisApiError, YokisAuthError
from custom_components.yokis.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import EMAIL, PASSWORD


async def test_user_flow_success(hass: HomeAssistant, mock_api: MagicMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["data"] == {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    # L'identifiant unique est l'email en minuscules : pas de doublon selon la casse.
    assert result["result"].unique_id == EMAIL.lower()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (YokisAuthError("refusé"), "invalid_auth"),
        (YokisApiError("réseau"), "cannot_connect"),
    ],
)
async def test_user_flow_errors_then_recover(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception, expected: str
) -> None:
    mock_api.async_login.side_effect = error
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "mauvais"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    # Le formulaire reste ouvert : une nouvelle saisie correcte aboutit.
    mock_api.async_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL.upper(), CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_api.async_login.assert_not_called()


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["email"] == EMAIL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "nouveau"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "nouveau"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (YokisAuthError("refusé"), "invalid_auth"),
        (YokisApiError("réseau"), "cannot_connect"),
    ],
)
async def test_reauth_flow_errors(
    hass: HomeAssistant,
    mock_api: MagicMock,
    config_entry: MockConfigEntry,
    error: Exception,
    expected: str,
) -> None:
    mock_api.async_login.side_effect = error
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "mauvais"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    # L'ancien mot de passe n'est pas écrasé tant que le nouveau n'est pas validé.
    assert config_entry.data[CONF_PASSWORD] == PASSWORD
