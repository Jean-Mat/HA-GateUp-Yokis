"""Coordinateur de l'état des appareils Yokis, mis à jour par le flux SSE temps réel."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import YokisApiClient, YokisApiError, YokisAuthError
from .const import (
    DOMAIN,
    HOME_EVENT_EQUIPMENTS_UPDATE,
    HOME_EVENT_FULL_UPDATE,
    HOME_EVENT_GATEWAY_OFFLINE,
    HOME_EVENT_GATEWAY_ONLINE,
    NOTIFS_RETRY_MAX_SECONDS,
    NOTIFS_RETRY_MIN_SECONDS,
    NOTIFS_STABLE_CONNECTION_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


# Entrée de configuration dont `runtime_data` contient le coordinateur.
YokisConfigEntry = ConfigEntry["YokisCoordinator"]


class YokisCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """État des équipements, indexé par uuid.

    Aucun polling : l'état est mis à jour en temps réel par le flux SSE
    `/notifs`. La liste complète n'est rechargée qu'au démarrage, après une
    reconnexion du flux, ou quand un événement le demande.
    """

    config_entry: YokisConfigEntry

    def __init__(self, hass: HomeAssistant, entry: YokisConfigEntry, api: YokisApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.api = api
        # Passerelle GATE-UP connectée au cloud : sans elle, aucun volet n'est pilotable.
        self.gateway_online = True

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            home_status = await self.api.async_get_home_status()
            equipments = await self.api.async_get_equipments()
        except YokisAuthError as err:
            # Lance automatiquement le flux de ré-authentification.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except YokisApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        self.gateway_online = bool((home_status or {}).get("online", True))
        return {equipment["uuid"]: equipment for equipment in equipments}

    async def async_listen_notifs(self) -> None:
        """Boucle d'écoute du flux SSE, avec reconnexion automatique.

        Tourne jusqu'à son annulation (déchargement de l'intégration), ou
        jusqu'à un refus des identifiants : inutile alors d'insister, la
        ré-authentification rechargera l'intégration.
        """
        retry_delay = NOTIFS_RETRY_MIN_SECONDS
        first_connection = True
        while True:
            if not first_connection:
                # Des changements ont pu être manqués pendant la coupure.
                await self.async_refresh()
            first_connection = False

            connected_at = time.monotonic()
            try:
                async for event in self.api.async_listen_notifs():
                    await self._async_handle_notif(event)
            except YokisAuthError as err:
                _LOGGER.warning("Identifiants Yokis refusés, arrêt du flux de notifications : %s", err)
                self.config_entry.async_start_reauth(self.hass)
                return
            except YokisApiError as err:
                _LOGGER.debug("Flux de notifications Yokis interrompu : %s", err)
            except Exception:  # noqa: BLE001 - la boucle ne doit jamais s'arrêter
                _LOGGER.exception("Erreur inattendue sur le flux de notifications Yokis")
            else:
                _LOGGER.debug("Flux de notifications Yokis fermé par le serveur")

            if time.monotonic() - connected_at >= NOTIFS_STABLE_CONNECTION_SECONDS:
                retry_delay = NOTIFS_RETRY_MIN_SECONDS
            _LOGGER.debug("Reconnexion au flux de notifications dans %s s", retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, NOTIFS_RETRY_MAX_SECONDS)

    async def _async_handle_notif(self, event: dict[str, Any]) -> None:
        _LOGGER.debug("Notification Yokis reçue : %s", event)
        event_type = event.get("type")
        if event_type == "EQUIPMENT_STATE":
            state = event.get("state") or {}
            uuid = state.get("uuid")
            if self.data is None or uuid not in self.data:
                # Équipement inconnu (ajouté depuis le dernier rafraîchissement).
                await self.async_request_refresh()
                return
            equipment = self.data[uuid]
            updated = {**equipment, "state": {**equipment.get("state", {}), **state}}
            self.async_set_updated_data({**self.data, uuid: updated})
        elif event_type == "HOME_STATE":
            await self._async_handle_home_event(event.get("eventType"))
        elif event_type == "EQUIPMENT_ADD":
            await self.async_request_refresh()
        elif event_type == "ERROR":
            _LOGGER.warning(
                "Erreur signalée par la passerelle Yokis : %s (code %s)",
                event.get("message"),
                event.get("gateErrorCode"),
            )

    async def _async_handle_home_event(self, home_event: int | None) -> None:
        if home_event == HOME_EVENT_GATEWAY_OFFLINE:
            _LOGGER.info("Passerelle Yokis hors ligne : volets indisponibles")
            self.gateway_online = False
            self.async_update_listeners()
        elif home_event == HOME_EVENT_GATEWAY_ONLINE:
            _LOGGER.info("Passerelle Yokis de nouveau en ligne")
            # Le rafraîchissement remet `gateway_online` à jour et récupère les
            # mouvements faits pendant la coupure.
            await self.async_request_refresh()
        elif home_event in (HOME_EVENT_FULL_UPDATE, HOME_EVENT_EQUIPMENTS_UPDATE):
            await self.async_request_refresh()
        # Les autres événements (scénarios, pièces, invités...) ne nous concernent pas.
