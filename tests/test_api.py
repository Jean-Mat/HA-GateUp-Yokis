"""Tests du client HTTP contre un faux serveur Yokis local (vrais échanges HTTP)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import itertools
import json
from unittest.mock import patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from custom_components.yokis import api as api_module
from custom_components.yokis.api import YokisApiClient, YokisApiError, YokisAuthError

from .conftest import HOME_ID, PASSWORD

EMAIL = "test@example.com"

# Le plugin de test de Home Assistant interdit les sockets ; on les autorise
# ici pour le faux serveur. Les connexions restent limitées à 127.0.0.1.
pytestmark = pytest.mark.usefixtures("socket_enabled")


class FakeYokisServer:
    """Imite les routes de l'API Yno UP utilisées par l'intégration."""

    def __init__(self) -> None:
        self.valid_tokens: set[str] = set()
        self._token_ids = itertools.count(1)
        self.signin_count = 0
        self.homes: list[dict] = [{"homeId": HOME_ID, "name": "Maison"}]
        self.signin_response: dict | None = None  # réponse forcée de /auth/signin
        self.reject_all_tokens = False
        self.commands: list[dict] = []
        self.sse_lines: list[str] = []
        self.sse_hang = False  # n'envoie rien après les en-têtes
        self.delay = 0.0

        self.app = web.Application()
        prefix = "/api/yno/v1"
        self.app.router.add_post(f"{prefix}/auth/signin", self._signin)
        self.app.router.add_get(f"{prefix}/homes", self._homes)
        self.app.router.add_get(f"{prefix}/homes/{{home}}", self._home_status)
        self.app.router.add_get(f"{prefix}/homes/{{home}}/equipments", self._equipments)
        self.app.router.add_post(f"{prefix}/homes/{{home}}/equipments/{{uuid}}/command", self._command)
        self.app.router.add_get(f"{prefix}/homes/{{home}}/notifs", self._notifs)

    def expire_tokens(self) -> None:
        self.valid_tokens.clear()

    def _authorized(self, request: web.Request) -> bool:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        return not self.reject_all_tokens and token in self.valid_tokens

    async def _signin(self, request: web.Request) -> web.Response:
        self.signin_count += 1
        body = await request.json()
        if body != {"login": EMAIL, "password": PASSWORD}:
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        if self.signin_response is not None:
            return web.json_response(self.signin_response)
        token = f"token-{next(self._token_ids)}"
        self.valid_tokens.add(token)
        return web.json_response({"token": token, "refreshToken": "r", "status": 0})

    async def _homes(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        return web.json_response(self.homes)

    async def _home_status(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        return web.json_response({"accessType": 0, "online": True})

    async def _equipments(self, request: web.Request) -> web.Response:
        await asyncio.sleep(self.delay)
        if not self._authorized(request):
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        return web.json_response([{"uuid": "u1", "name": "Volet", "deviceType": 103}])

    async def _command(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        self.commands.append({"uuid": request.match_info["uuid"], "body": await request.json()})
        return web.Response(status=200)  # corps vide, comme la vraie API

    async def _notifs(self, request: web.Request) -> web.StreamResponse:
        if not self._authorized(request):
            return web.json_response({"message": "UNAUTHORIZED"}, status=401)
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        if self.sse_hang:
            await asyncio.sleep(10)
        for line in self.sse_lines:
            await resp.write(f"{line}\n".encode())
        return resp  # fin de la réponse = flux fermé par le serveur


@pytest.fixture
async def server() -> AsyncIterator[FakeYokisServer]:
    fake = FakeYokisServer()
    test_server = TestServer(fake.app)
    await test_server.start_server()
    with patch.object(api_module, "API_BASE_URL", str(test_server.make_url("/api/yno/v1"))):
        yield fake
    await test_server.close()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def client(session: aiohttp.ClientSession) -> YokisApiClient:
    return YokisApiClient(session, EMAIL, PASSWORD)


async def _collect(client: YokisApiClient) -> list[dict]:
    return [event async for event in client.async_listen_notifs()]


# --- Connexion -------------------------------------------------------------


async def test_login(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    assert client.home_id == HOME_ID
    assert server.signin_count == 1


async def test_login_wrong_password(server: FakeYokisServer, session: aiohttp.ClientSession) -> None:
    client = YokisApiClient(session, EMAIL, "mauvais")
    with pytest.raises(YokisAuthError):
        await client.async_login()


@pytest.mark.parametrize(
    ("signin_response", "homes"),
    [
        ({"status": 0}, [{"homeId": HOME_ID}]),  # pas de token
        (None, []),  # aucune maison
        (None, [{"name": "sans homeId"}]),
    ],
)
async def test_login_unexpected_response(
    server: FakeYokisServer, client: YokisApiClient, signin_response: dict | None, homes: list
) -> None:
    server.signin_response = signin_response
    server.homes = homes
    with pytest.raises(YokisApiError):
        await client.async_login()


async def test_login_homes_unauthorized_does_not_loop(
    server: FakeYokisServer, client: YokisApiClient
) -> None:
    # Un 401 sur /homes juste après la connexion ne doit pas relancer de connexion.
    server.reject_all_tokens = True
    with pytest.raises(YokisAuthError):
        await client.async_login()
    assert server.signin_count == 1


async def test_request_without_login(server: FakeYokisServer, client: YokisApiClient) -> None:
    with pytest.raises(YokisApiError):
        await client.async_get_equipments()


# --- Token expiré (401) ----------------------------------------------------


async def test_expired_token_relogin_once(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    server.expire_tokens()

    equipments = await client.async_get_equipments()

    assert equipments[0]["uuid"] == "u1"
    assert server.signin_count == 2
    # `home_id` est conservé : seul le token est renouvelé.
    assert client.home_id == HOME_ID


async def test_concurrent_401_single_relogin(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    server.expire_tokens()

    results = await asyncio.gather(*(client.async_get_equipments() for _ in range(3)))

    assert all(result[0]["uuid"] == "u1" for result in results)
    assert server.signin_count == 2  # un seul re-login grâce au verrou


async def test_persistent_401_raises_auth_error(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    server.reject_all_tokens = True

    with pytest.raises(YokisAuthError):
        await client.async_get_equipments()
    assert server.signin_count == 2  # une seule tentative, pas de récursion


async def test_relogin_with_changed_password(
    server: FakeYokisServer, session: aiohttp.ClientSession
) -> None:
    client = YokisApiClient(session, EMAIL, PASSWORD)
    await client.async_login()
    server.expire_tokens()
    client._password = "ancien"  # le mot de passe a changé côté Yokis

    with pytest.raises(YokisAuthError):
        await client.async_get_equipments()


async def test_timeout(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    server.delay = 1
    with (
        patch.object(api_module, "_TIMEOUT", aiohttp.ClientTimeout(total=0.1)),
        pytest.raises(YokisApiError, match="Délai dépassé"),
    ):
        await client.async_get_equipments()


async def test_network_error(session: aiohttp.ClientSession) -> None:
    client = YokisApiClient(session, EMAIL, PASSWORD)
    # Port 1 : rien n'écoute, connexion refusée.
    with (
        patch.object(api_module, "API_BASE_URL", "http://127.0.0.1:1/api/yno/v1"),
        pytest.raises(YokisApiError),
    ):
        await client.async_login()


# --- Commandes -------------------------------------------------------------


async def test_send_command(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    await client.async_send_command("u1", "open")
    await client.async_send_command("u1", "liftPercentage", {"liftPercentage": 42})

    assert server.commands == [
        {"uuid": "u1", "body": {"order": "open"}},
        {"uuid": "u1", "body": {"order": "liftPercentage", "params": {"liftPercentage": 42}}},
    ]


async def test_home_status(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    assert await client.async_get_home_status() == {"accessType": 0, "online": True}


# --- Flux SSE --------------------------------------------------------------


async def test_notifs_parsing(server: FakeYokisServer, client: YokisApiClient) -> None:
    event1 = {"type": "EQUIPMENT_STATE", "state": {"uuid": "u1", "percentage": 53}}
    event2 = {"type": "HOME_STATE", "eventType": 7}
    # Même format que le vrai flux (capturé le 2026-10-16).
    server.sse_lines = [
        "retry:2000",
        "",
        "event:message",
        "id:cd1b09e4-6c06-4071-87e4-4eec5cd82726",
        f"data:{json.dumps(event1)}",
        "",
        ":",  # keep-alive
        "",
        "event:message",
        "data:pas du json",
        "",
        f"data: {json.dumps(event2)}",  # espace après `data:` autorisé
        "",
    ]
    await client.async_login()

    # Le JSON invalide est ignoré ; le générateur se termine quand le serveur ferme le flux.
    assert await _collect(client) == [event1, event2]


async def test_notifs_crlf_and_multiline_data(server: FakeYokisServer, client: YokisApiClient) -> None:
    server.sse_lines = ['data:{"type":\r', 'data:"ERROR"}\r', "\r"]
    await client.async_login()
    assert await _collect(client) == [{"type": "ERROR"}]


async def test_notifs_expired_token(server: FakeYokisServer, client: YokisApiClient) -> None:
    server.sse_lines = ['data:{"type":"HOME_STATE","eventType":8}', ""]
    await client.async_login()
    server.expire_tokens()

    assert await _collect(client) == [{"type": "HOME_STATE", "eventType": 8}]
    assert server.signin_count == 2


async def test_notifs_persistent_401(server: FakeYokisServer, client: YokisApiClient) -> None:
    await client.async_login()
    server.reject_all_tokens = True
    with pytest.raises(YokisAuthError):
        await _collect(client)


async def test_notifs_silence_raises(server: FakeYokisServer, client: YokisApiClient) -> None:
    server.sse_hang = True
    await client.async_login()
    timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=0.1)
    with patch.object(api_module, "_NOTIFS_TIMEOUT", timeout), pytest.raises(YokisApiError):
        await _collect(client)
