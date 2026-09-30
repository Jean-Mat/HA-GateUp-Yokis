"""Plateforme `cover` : expose les volets Yokis comme entités Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YokisCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: YokisCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        YokisCover(coordinator, uuid)
        for uuid, equipment in coordinator.data.items()
        if equipment.get("state", {}).get("percentage") is not None
    ]
    async_add_entities(entities)


class YokisCover(CoordinatorEntity[YokisCoordinator], CoverEntity):
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, coordinator: YokisCoordinator, uuid: str) -> None:
        super().__init__(coordinator)
        self._uuid = uuid
        self._attr_unique_id = uuid

        equipment = coordinator.data[uuid]
        self._attr_name = equipment["name"]
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
        return self.coordinator.data[self._uuid]

    @property
    def current_cover_position(self) -> int | None:
        return self._equipment.get("state", {}).get("percentage")

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return position == 0 if position is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_send_command(self._uuid, "open")
        await self.coordinator.async_request_refresh()
        self.coordinator.async_start_fast_poll_burst()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_send_command(self._uuid, "close")
        await self.coordinator.async_request_refresh()
        self.coordinator.async_start_fast_poll_burst()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_send_command(self._uuid, "stop")
        await self.coordinator.async_request_refresh()
        self.coordinator.async_start_fast_poll_burst()
