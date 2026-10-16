"""Fixtures communes : données d'exemple, client API simulé, entrée de configuration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yokis.const import DOMAIN
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

EMAIL = "Test@Example.com"
PASSWORD = "secret"
HOME_ID = "HOME1"

UUID_BUREAU = "aaaaaaaa-0000-4000-8000-000000000001"
UUID_SALON = "aaaaaaaa-0000-4000-8000-000000000002"
UUID_ZIGBEE = "11111111-2222-3333-4444-555555555555"
UUID_LUMIERE = "99999999-8888-7777-6666-555555555555"


def make_equipment(uuid: str, name: str, device_type: int, percentage: int | None, model: str) -> dict:
    state: dict[str, Any] = {"alive": 2, "type": device_type, "uuid": uuid}
    if percentage is not None:
        state["percentage"] = percentage
    return {
        "uuid": uuid,
        "name": name,
        "deviceType": device_type,
        "state": state,
        "informations": {
            "manufacturerName": "YOKIS",
            "modelIdentifier": model,
            "softVersion": "5.3.0",
        },
    }


# Même structure que la réponse réelle de GET /homes/{homeId}/equipments.
EQUIPMENTS = [
    make_equipment(UUID_BUREAU, "Volets bureau", 103, 100, "MVR500E-UP"),
    make_equipment(UUID_SALON, "Volet salon", 103, 0, "MVR500E-UP"),
    make_equipment(UUID_ZIGBEE, "Volet zigbee", 202, 50, "Generic MVR"),
    # Module d'éclairage (MTR) : ne doit pas devenir un volet, même avec un pourcentage.
    make_equipment(UUID_LUMIERE, "Lumière entrée", 100, 80, "MTR500E-UP"),
]


class FakeNotifs:
    """Flux SSE simulé : les tests y poussent des événements ou des exceptions."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any] | Exception] = asyncio.Queue()
        self.connections = 0

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        self.connections += 1
        while True:
            item = await self.queue.get()
            if isinstance(item, Exception):
                self.queue.task_done()
                raise item
            yield item
            # On n'arrive ici qu'une fois l'événement traité par le coordinateur.
            self.queue.task_done()

    async def push(self, hass: HomeAssistant, item: dict[str, Any] | Exception) -> None:
        """Envoie un événement et attend qu'il soit entièrement traité."""
        await self.queue.put(item)
        await self.queue.join()
        await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Autorise le chargement de `custom_components/yokis` dans tous les tests."""


@pytest.fixture
def fake_notifs() -> FakeNotifs:
    return FakeNotifs()


@pytest.fixture
def mock_api(fake_notifs: FakeNotifs) -> Generator[MagicMock]:
    """Remplace YokisApiClient dans `__init__.py` et `config_flow.py`."""
    api = MagicMock()
    api.home_id = HOME_ID
    api.async_login = AsyncMock()
    api.async_get_home_status = AsyncMock(return_value={"accessType": 0, "online": True})
    # État « côté serveur », modifiable par les tests. Chaque appel en renvoie
    # une copie, comme une vraie réponse HTTP : sinon le coordinateur et le
    # test partageraient les mêmes objets.
    api.equipments = copy.deepcopy(EQUIPMENTS)
    api.async_get_equipments = AsyncMock(side_effect=lambda: copy.deepcopy(api.equipments))
    api.async_send_command = AsyncMock()
    api.async_listen_notifs = fake_notifs.listen

    with (
        patch("custom_components.yokis.YokisApiClient", return_value=api),
        patch("custom_components.yokis.config_flow.YokisApiClient", return_value=api),
    ):
        yield api


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=EMAIL.lower(),
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: MagicMock
) -> MockConfigEntry:
    """Intégration chargée avec le client API simulé."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
