"""Plateforme `cover` : expose les volets Yokis comme entités Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import YokisApiError, YokisAuthError
from .const import ALIVE_NOT_ALIVE, COVER_DEVICE_TYPES, DOMAIN, SET_POSITION_DEVICE_TYPES
from .coordinator import YokisConfigEntry, YokisCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: YokisConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known_uuids: set[str] = set()

    @callback
    def _async_add_new_covers() -> None:
        # Appelé au démarrage puis à chaque mise à jour : un volet ajouté dans
        # l'app Yno UP (événement EQUIPMENT_ADD → rechargement) apparaît sans
        # avoir à recharger l'intégration.
        new_uuids = [
            uuid
            for uuid, equipment in coordinator.data.items()
            if uuid not in known_uuids and equipment.get("deviceType") in COVER_DEVICE_TYPES
        ]
        if new_uuids:
            known_uuids.update(new_uuids)
            async_add_entities(YokisCover(coordinator, uuid) for uuid in new_uuids)

    _async_add_new_covers()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_covers))


class YokisCover(CoordinatorEntity[YokisCoordinator], CoverEntity):
    _attr_device_class = CoverDeviceClass.SHUTTER
    # Le volet est la fonction principale de l'appareil : l'entité prend
    # simplement le nom de l'appareil (celui du module dans l'app Yno UP).
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: YokisCoordinator, uuid: str) -> None:
        super().__init__(coordinator)
        self._uuid = uuid
        self._attr_unique_id = uuid

        equipment = coordinator.data[uuid]
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        if equipment.get("deviceType") in SET_POSITION_DEVICE_TYPES:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
        informations = equipment.get("informations", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uuid)},
            name=equipment["name"],
            manufacturer=informations.get("manufacturerName", "Yokis"),
            model=informations.get("modelIdentifier"),
            sw_version=informations.get("softVersion"),
        )

    @property
    def _equipment(self) -> dict:
        # L'équipement peut disparaître du compte (supprimé dans l'app Yno UP).
        return self.coordinator.data.get(self._uuid, {})

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._uuid in self.coordinator.data
            and self.coordinator.gateway_online
            # `alive` inconnu (0) : on laisse le volet disponible plutôt que de le masquer.
            and self._equipment.get("state", {}).get("alive") != ALIVE_NOT_ALIVE
        )

    @property
    def current_cover_position(self) -> int | None:
        return self._equipment.get("state", {}).get("percentage")

    @property
    def is_closed(self) -> bool | None:
        # Même convention que Home Assistant (vérifié sur un MVR500E-UP) :
        # 0 = fermé, 100 = ouvert.
        position = self.current_cover_position
        return position == 0 if position is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_send_command("open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_send_command("close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_send_command("stop")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._async_send_command(
            "liftPercentage", {"liftPercentage": kwargs[ATTR_POSITION]}
        )

    async def _async_send_command(self, order: str, params: dict[str, Any] | None = None) -> None:
        try:
            await self.coordinator.api.async_send_command(self._uuid, order, params)
        except YokisApiError as err:
            if isinstance(err, YokisAuthError):
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={
                    "order": order,
                    # `self.name` vaut None : le nom vient de l'appareil.
                    "name": self._equipment.get("name", self._uuid),
                    "error": str(err),
                },
            ) from err
        # Pas de rafraîchissement ici : la nouvelle position arrivera par le flux SSE.
