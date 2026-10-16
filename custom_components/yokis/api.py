"""Client HTTP asynchrone pour l'API cloud Yokis "Yno UP"."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL, NOTIFS_READ_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
# Flux SSE : pas de durée totale, mais le serveur envoie un keep-alive toutes
# les 10 s, donc un silence prolongé signifie une connexion morte.
_NOTIFS_TIMEOUT = aiohttp.ClientTimeout(
    total=None, connect=REQUEST_TIMEOUT_SECONDS, sock_read=NOTIFS_READ_TIMEOUT_SECONDS
)


class YokisApiError(Exception):
    """Erreur générique retournée par l'API Yokis."""


class YokisAuthError(YokisApiError):
    """Identifiants invalides ou session expirée."""


class YokisApiClient:
    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._relogin_lock = asyncio.Lock()
        self.home_id: str | None = None

    async def async_login(self) -> None:
        """Connexion complète : obtention du token puis de la maison à piloter."""
        await self._async_signin()

        # Token tout neuf : un 401 ici ne doit pas relancer une connexion.
        homes = await self._async_request("GET", "/homes", retry_on_401=False)
        if not homes:
            raise YokisApiError("Aucune maison Yokis associée à ce compte")
        try:
            self.home_id = homes[0]["homeId"]
        except (KeyError, TypeError) as err:
            raise YokisApiError("Réponse inattendue de l'API (liste des maisons)") from err

    async def _async_signin(self) -> None:
        """Obtient un nouveau token (sans toucher à `home_id`)."""
        try:
            async with self._session.post(
                f"{API_BASE_URL}/auth/signin",
                json={"login": self._email, "password": self._password},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 401 or resp.status == 400:
                    raise YokisAuthError(f"Connexion refusée (status {resp.status})")
                resp.raise_for_status()
                data = await resp.json()
        except TimeoutError as err:
            raise YokisApiError("Délai dépassé lors de la connexion") from err
        except aiohttp.ClientError as err:
            raise YokisApiError(f"Erreur réseau lors de la connexion : {err}") from err

        try:
            self._token = data["token"]
        except (KeyError, TypeError) as err:
            raise YokisApiError("Réponse inattendue de l'API (connexion)") from err

    async def _async_relogin(self, expired_token: str | None) -> None:
        """Renouvelle le token après un 401.

        Le verrou évite que plusieurs appels simultanés (flux SSE, commandes...)
        se reconnectent chacun de leur côté : si le token a déjà été renouvelé
        pendant l'attente, on réutilise le nouveau.
        """
        async with self._relogin_lock:
            if self._token == expired_token:
                await self._async_signin()

    async def async_get_home_status(self) -> dict[str, Any]:
        """État de la maison, dont `online` : passerelle connectée au cloud."""
        return await self._async_request("GET", f"/homes/{self.home_id}")

    async def async_get_equipments(self) -> list[dict[str, Any]]:
        return await self._async_request("GET", f"/homes/{self.home_id}/equipments")

    async def async_send_command(
        self, uuid: str, order: str, params: dict[str, Any] | None = None
    ) -> None:
        body: dict[str, Any] = {"order": order}
        if params is not None:
            body["params"] = params
        await self._async_request(
            "POST", f"/homes/{self.home_id}/equipments/{uuid}/command", json=body
        )

    async def async_listen_notifs(self) -> AsyncIterator[dict[str, Any]]:
        """Écoute le flux SSE de la maison et renvoie le contenu JSON de chaque événement.

        Ne se termine que si le serveur ferme la connexion ; lève YokisApiError
        en cas d'erreur réseau ou de silence prolongé.
        """
        if self._token is None:
            raise YokisApiError("Client non authentifié, appeler async_login() d'abord")

        url = f"{API_BASE_URL}/homes/{self.home_id}/notifs"
        try:
            token = self._token
            resp = await self._async_open_notifs(url)
            if resp.status == 401:
                # Token probablement expiré : on retente une fois après re-login.
                resp.release()
                await self._async_relogin(token)
                resp = await self._async_open_notifs(url)
            async with resp:
                if resp.status == 401:
                    raise YokisAuthError("Accès refusé au flux de notifications")
                resp.raise_for_status()
                data_lines: list[str] = []
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                    if line:
                        # Seules les lignes `data:` nous intéressent (`event:`, `id:`,
                        # `retry:` et les commentaires `:` de keep-alive sont ignorés).
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                        continue
                    # Ligne vide = fin de l'événement.
                    if data_lines:
                        payload = "\n".join(data_lines)
                        data_lines = []
                        try:
                            yield json.loads(payload)
                        except ValueError:
                            _LOGGER.warning("Notification Yokis illisible : %s", payload)
        except TimeoutError as err:
            raise YokisApiError("Aucune donnée reçue sur le flux de notifications") from err
        except aiohttp.ClientError as err:
            raise YokisApiError(f"Erreur réseau sur le flux de notifications : {err}") from err

    async def _async_open_notifs(self, url: str) -> aiohttp.ClientResponse:
        return await self._session.get(
            url,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "text/event-stream"},
            timeout=_NOTIFS_TIMEOUT,
        )

    async def _async_request(
        self, method: str, path: str, *, retry_on_401: bool = True, **kwargs
    ) -> Any:
        if self._token is None:
            raise YokisApiError("Client non authentifié, appeler async_login() d'abord")

        token = self._token
        try:
            async with self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
                **kwargs,
            ) as resp:
                if resp.status != 401:
                    resp.raise_for_status()
                    return await _read_json_or_none(resp)
            if not retry_on_401:
                raise YokisAuthError(f"Accès refusé ({method} {path})")

            # Token probablement expiré : on retente une seule fois après re-login.
            await self._async_relogin(token)
            async with self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=_TIMEOUT,
                **kwargs,
            ) as retry_resp:
                if retry_resp.status == 401:
                    raise YokisAuthError(f"Accès refusé ({method} {path})")
                retry_resp.raise_for_status()
                return await _read_json_or_none(retry_resp)
        except TimeoutError as err:
            raise YokisApiError(f"Délai dépassé ({method} {path})") from err
        except aiohttp.ClientError as err:
            raise YokisApiError(f"Erreur réseau ({method} {path}) : {err}") from err


async def _read_json_or_none(resp: aiohttp.ClientResponse) -> Any:
    # Les endpoints de commande renvoient un 200 avec un corps vide.
    text = await resp.text()
    return await resp.json() if text else None
