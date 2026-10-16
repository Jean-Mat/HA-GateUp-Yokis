"""Tests des entités `cover` : état, commandes et mises à jour par le flux SSE."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yokis.api import YokisApiError, YokisAuthError
from custom_components.yokis.const import DOMAIN
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    CoverEntityFeature,
    CoverState,
)
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import UUID_BUREAU, UUID_SALON, FakeNotifs, make_equipment

BUREAU = "cover.volets_bureau"
SALON = "cover.volet_salon"
ZIGBEE = "cover.volet_zigbee"


def _equipment_state(uuid: str, **state) -> dict:
    return {"type": "EQUIPMENT_STATE", "state": {"uuid": uuid, "alive": 2, "type": 103, **state}}


def _home_state(event_type: int) -> dict:
    return {"type": "HOME_STATE", "eventType": event_type}


def _set_server_position(mock_api: MagicMock, uuid: str, percentage: int) -> None:
    """Change la position renvoyée par le prochain GET /equipments."""
    next(e for e in mock_api.equipments if e["uuid"] == uuid)["state"]["percentage"] = percentage


@pytest.mark.usefixtures("setup_integration")
async def test_entities_created_for_covers_only(hass: HomeAssistant) -> None:
    # Le module d'éclairage (deviceType 100) est ignoré malgré son pourcentage.
    assert sorted(hass.states.async_entity_ids(COVER_DOMAIN)) == [SALON, ZIGBEE, BUREAU]


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    "event",
    [
        {"type": "EQUIPMENT_ADD", "equipment": {}},
        # Premier état d'un équipement inconnu, sans EQUIPMENT_ADD préalable.
        _equipment_state("22222222-0000-0000-0000-000000000000", percentage=30),
    ],
)
async def test_new_cover_added_without_reload(
    hass: HomeAssistant, mock_api: MagicMock, fake_notifs: FakeNotifs, event: dict
) -> None:
    mock_api.equipments.append(
        make_equipment("22222222-0000-0000-0000-000000000000", "Volet cuisine", 103, 30, "MVR500E-UP")
    )
    mock_api.equipments.append(
        make_equipment("33333333-0000-0000-0000-000000000000", "Lumière cuisine", 100, 10, "MTR500E-UP")
    )

    await fake_notifs.push(hass, event)

    state = hass.states.get("cover.volet_cuisine")
    assert state is not None
    assert state.attributes[ATTR_CURRENT_POSITION] == 30
    # Toujours pas d'entité pour un module d'éclairage.
    assert len(hass.states.async_entity_ids(COVER_DOMAIN)) == 4


@pytest.mark.usefixtures("setup_integration")
async def test_no_duplicate_entities_on_refresh(
    hass: HomeAssistant, fake_notifs: FakeNotifs, caplog: pytest.LogCaptureFixture
) -> None:
    await fake_notifs.push(hass, _home_state(1))
    await fake_notifs.push(hass, _equipment_state(UUID_BUREAU, percentage=10))

    assert len(hass.states.async_entity_ids(COVER_DOMAIN)) == 3
    assert len(er.async_entries_for_config_entry(er.async_get(hass), _entry_id(hass))) == 3
    # Home Assistant écarte lui-même un doublon, mais en le signalant dans les logs.
    assert "does not generate unique IDs" not in caplog.text


def _entry_id(hass: HomeAssistant) -> str:
    return hass.config_entries.async_entries(DOMAIN)[0].entry_id


@pytest.mark.usefixtures("setup_integration")
async def test_entity_registry_and_device(hass: HomeAssistant) -> None:
    entry = er.async_get(hass).async_get(BUREAU)
    assert entry is not None
    assert entry.unique_id == UUID_BUREAU

    device = hass.data["device_registry"].async_get(entry.device_id)
    assert device.manufacturer == "YOKIS"
    assert device.model == "MVR500E-UP"
    assert device.sw_version == "5.3.0"


@pytest.mark.usefixtures("setup_integration")
async def test_entity_name(hass: HomeAssistant) -> None:
    entry = er.async_get(hass).async_get(BUREAU)
    assert entry.has_entity_name
    assert entry.original_name is None  # nom hérité de l'appareil
    assert hass.states.get(BUREAU).attributes["friendly_name"] == "Volets bureau"


@pytest.mark.usefixtures("setup_integration")
async def test_initial_state(hass: HomeAssistant) -> None:
    bureau = hass.states.get(BUREAU)
    assert bureau.state == CoverState.OPEN
    assert bureau.attributes[ATTR_CURRENT_POSITION] == 100

    salon = hass.states.get(SALON)
    assert salon.state == CoverState.CLOSED
    assert salon.attributes[ATTR_CURRENT_POSITION] == 0


@pytest.mark.usefixtures("setup_integration")
async def test_supported_features(hass: HomeAssistant) -> None:
    base = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    assert hass.states.get(BUREAU).attributes[ATTR_SUPPORTED_FEATURES] == (
        base | CoverEntityFeature.SET_POSITION
    )
    # Pas d'ordre `liftPercentage` pour un MVR Zigbee générique.
    assert hass.states.get(ZIGBEE).attributes[ATTR_SUPPORTED_FEATURES] == base


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("service", "data", "order", "params"),
    [
        (SERVICE_OPEN_COVER, {}, "open", None),
        (SERVICE_CLOSE_COVER, {}, "close", None),
        (SERVICE_STOP_COVER, {}, "stop", None),
        (SERVICE_SET_COVER_POSITION, {ATTR_POSITION: 42}, "liftPercentage", {"liftPercentage": 42}),
    ],
)
async def test_commands(
    hass: HomeAssistant, mock_api: MagicMock, service: str, data: dict, order: str, params
) -> None:
    await hass.services.async_call(
        COVER_DOMAIN, service, {ATTR_ENTITY_ID: BUREAU, **data}, blocking=True
    )
    mock_api.async_send_command.assert_awaited_once_with(UUID_BUREAU, order, params)


@pytest.mark.usefixtures("setup_integration")
async def test_command_error(hass: HomeAssistant, mock_api: MagicMock) -> None:
    mock_api.async_send_command.side_effect = YokisApiError("Délai dépassé")

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: BUREAU}, blocking=True
        )
    assert exc_info.value.translation_key == "command_failed"
    assert exc_info.value.translation_placeholders == {
        "order": "open",
        "name": "Volets bureau",
        "error": "Délai dépassé",
    }
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


@pytest.mark.usefixtures("setup_integration")
async def test_command_auth_error_starts_reauth(hass: HomeAssistant, mock_api: MagicMock) -> None:
    mock_api.async_send_command.side_effect = YokisAuthError("refusé")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: BUREAU}, blocking=True
        )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.usefixtures("setup_integration")
async def test_sse_position_update(hass: HomeAssistant, fake_notifs: FakeNotifs) -> None:
    await fake_notifs.push(hass, _equipment_state(UUID_BUREAU, percentage=35))

    bureau = hass.states.get(BUREAU)
    assert bureau.state == CoverState.OPEN
    assert bureau.attributes[ATTR_CURRENT_POSITION] == 35

    await fake_notifs.push(hass, _equipment_state(UUID_BUREAU, percentage=0))
    assert hass.states.get(BUREAU).state == CoverState.CLOSED
    # Les autres volets ne bougent pas.
    assert hass.states.get(SALON).attributes[ATTR_CURRENT_POSITION] == 0


@pytest.mark.usefixtures("setup_integration")
async def test_sse_module_not_alive(hass: HomeAssistant, fake_notifs: FakeNotifs) -> None:
    await fake_notifs.push(hass, _equipment_state(UUID_BUREAU, alive=1))
    assert hass.states.get(BUREAU).state == STATE_UNAVAILABLE
    assert hass.states.get(SALON).state == CoverState.CLOSED

    # `alive` inconnu (0) : le volet reste disponible.
    await fake_notifs.push(hass, _equipment_state(UUID_BUREAU, alive=0))
    assert hass.states.get(BUREAU).state == CoverState.OPEN


@pytest.mark.usefixtures("setup_integration")
async def test_sse_gateway_offline_then_online(
    hass: HomeAssistant, mock_api: MagicMock, fake_notifs: FakeNotifs
) -> None:
    await fake_notifs.push(hass, _home_state(7))
    for entity_id in (BUREAU, SALON, ZIGBEE):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # Pendant la coupure, le volet du salon a été ouvert à l'interrupteur.
    _set_server_position(mock_api, UUID_SALON, 100)

    await fake_notifs.push(hass, _home_state(8))
    assert hass.states.get(BUREAU).state == CoverState.OPEN
    assert hass.states.get(SALON).attributes[ATTR_CURRENT_POSITION] == 100


async def test_gateway_offline_at_startup(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_get_home_status.return_value = {"accessType": 0, "online": False}
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(BUREAU).state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("event", "refresh_expected"),
    [
        (_home_state(0), True),  # FULL_UPDATE
        (_home_state(1), True),  # EQUIPMENTS_UPDATE
        (_home_state(3), False),  # SCENARIOS_UPDATE : ignoré
        ({"type": "EQUIPMENT_ADD", "equipment": {}}, True),
        (_equipment_state("uuid-inconnu", percentage=10), True),
        ({"type": "ROOM_STATE", "state": {"uuid": "piece"}}, False),
        ({"type": "ERROR", "gateErrorCode": 321, "message": "ERR_MAX_EQUIPMENT_REACHED"}, False),
    ],
)
async def test_sse_events_refresh(
    hass: HomeAssistant,
    mock_api: MagicMock,
    fake_notifs: FakeNotifs,
    event: dict,
    refresh_expected: bool,
) -> None:
    calls_before = mock_api.async_get_equipments.await_count
    await fake_notifs.push(hass, event)
    assert (mock_api.async_get_equipments.await_count > calls_before) is refresh_expected


@pytest.mark.usefixtures("setup_integration")
async def test_sse_reconnects_and_resyncs(
    hass: HomeAssistant, mock_api: MagicMock, fake_notifs: FakeNotifs
) -> None:
    # Le volet du bureau bouge pendant la coupure du flux.
    _set_server_position(mock_api, UUID_BUREAU, 20)

    with patch("custom_components.yokis.coordinator.NOTIFS_RETRY_MIN_SECONDS", 0):
        await fake_notifs.push(hass, YokisApiError("Aucune donnée reçue"))
        # Reconnexion immédiate (attente réduite à 0 s) : on vérifie qu'elle
        # fonctionne en envoyant un événement sur le nouveau flux.
        await fake_notifs.push(hass, _equipment_state(UUID_SALON, percentage=60))

    assert fake_notifs.connections == 2
    # Rechargement complet après la reconnexion.
    assert hass.states.get(BUREAU).attributes[ATTR_CURRENT_POSITION] == 20
    assert hass.states.get(SALON).attributes[ATTR_CURRENT_POSITION] == 60


@pytest.mark.usefixtures("setup_integration")
async def test_sse_auth_error_stops_and_starts_reauth(
    hass: HomeAssistant, fake_notifs: FakeNotifs
) -> None:
    with patch("custom_components.yokis.coordinator.NOTIFS_RETRY_MIN_SECONDS", 0):
        await fake_notifs.push(hass, YokisAuthError("refusé"))
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    # Pas de reconnexion avec des identifiants refusés.
    assert fake_notifs.connections == 1
