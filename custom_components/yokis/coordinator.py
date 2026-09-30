"""Coordinateur de mise à jour périodique de l'état des appareils Yokis."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import YokisApiClient, YokisApiError
from .const import (
    DOMAIN,
    FAST_POLL_DURATION_SECONDS,
    FAST_POLL_INTERVAL_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class YokisCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Récupère périodiquement la liste des équipements et leur état, indexés par uuid."""

    def __init__(self, hass: HomeAssistant, api: YokisApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.api = api
        self._fast_poll_task: asyncio.Task | None = None

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            equipments = await self.api.async_get_equipments()
        except YokisApiError as err:
            raise UpdateFailed(str(err)) from err

        return {equipment["uuid"]: equipment for equipment in equipments}

    def async_start_fast_poll_burst(self) -> None:
        """Rafraîchit plus fréquemment pendant quelques secondes (après une commande)."""
        if self._fast_poll_task is not None and not self._fast_poll_task.done():
            self._fast_poll_task.cancel()
        self._fast_poll_task = self.hass.async_create_task(self._async_fast_poll_burst())

    async def _async_fast_poll_burst(self) -> None:
        iterations = FAST_POLL_DURATION_SECONDS // FAST_POLL_INTERVAL_SECONDS
        try:
            for _ in range(iterations):
                await asyncio.sleep(FAST_POLL_INTERVAL_SECONDS)
                await self.async_request_refresh()
                if not self.last_update_success:
                    # Ne pas insister si l'API est en erreur (ex: throttling côté serveur).
                    _LOGGER.debug("Arrêt du burst de rafraîchissement après un échec")
                    break
        except asyncio.CancelledError:
            pass

    def async_shutdown_fast_poll(self) -> None:
        if self._fast_poll_task is not None and not self._fast_poll_task.done():
            self._fast_poll_task.cancel()
