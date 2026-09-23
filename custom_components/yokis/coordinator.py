"""Coordinateur de mise à jour périodique de l'état des appareils Yokis."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import YokisApiClient, YokisApiError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

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

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            equipments = await self.api.async_get_equipments()
        except YokisApiError as err:
            raise UpdateFailed(str(err)) from err

        return {equipment["uuid"]: equipment for equipment in equipments}
