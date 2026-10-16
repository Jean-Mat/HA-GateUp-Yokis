"""Intégration Home Assistant pour les volets Yokis via l'API cloud Yno UP."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import YokisApiClient, YokisApiError, YokisAuthError
from .const import DOMAIN
from .coordinator import YokisConfigEntry, YokisCoordinator

PLATFORMS = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: YokisConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = YokisApiClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])

    try:
        await api.async_login()
    except YokisAuthError as err:
        # Mot de passe changé, compte supprimé... : Home Assistant propose la ré-authentification.
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    except YokisApiError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="setup_failed",
            translation_placeholders={"error": str(err)},
        ) from err

    coordinator = YokisCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Tâche annulée automatiquement au déchargement de l'intégration.
    entry.async_create_background_task(
        hass, coordinator.async_listen_notifs(), f"{DOMAIN}_notifs_{entry.entry_id}"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: YokisConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
