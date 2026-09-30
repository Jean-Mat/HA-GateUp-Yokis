"""Intégration Home Assistant pour les volets Yokis via l'API cloud Yno UP."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import YokisApiClient, YokisApiError
from .const import DOMAIN
from .coordinator import YokisCoordinator

PLATFORMS = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = YokisApiClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])

    try:
        await api.async_login()
    except YokisApiError as err:
        raise ConfigEntryNotReady(f"Impossible de se connecter à Yokis : {err}") from err

    coordinator = YokisCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: YokisCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_shutdown_fast_poll()
    return unload_ok
