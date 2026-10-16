"""Écran de configuration Home Assistant pour Yokis (email/mot de passe Yno UP)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import YokisApiClient, YokisApiError, YokisAuthError
from .const import DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class YokisConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            errors = await self._async_validate(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if not errors:
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Lancé par Home Assistant quand l'API refuse les identifiants enregistrés."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            errors = await self._async_validate(email, user_input[CONF_PASSWORD])
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"email": email},
            errors=errors,
        )

    async def _async_validate(self, email: str, password: str) -> dict[str, str]:
        """Tente une connexion ; renvoie les erreurs à afficher dans le formulaire."""
        api = YokisApiClient(async_get_clientsession(self.hass), email, password)
        try:
            await api.async_login()
        except YokisAuthError:
            return {"base": "invalid_auth"}
        except YokisApiError:
            return {"base": "cannot_connect"}
        return {}
