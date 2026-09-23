"""Client HTTP asynchrone pour l'API cloud Yokis "Yno UP"."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_BASE_URL


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
        self.home_id: str | None = None

    async def async_login(self) -> None:
        try:
            async with self._session.post(
                f"{API_BASE_URL}/auth/signin",
                json={"login": self._email, "password": self._password},
            ) as resp:
                if resp.status == 401 or resp.status == 400:
                    raise YokisAuthError(f"Connexion refusée (status {resp.status})")
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise YokisApiError(f"Erreur réseau lors de la connexion : {err}") from err

        self._token = data["token"]

        homes = await self._async_request("GET", "/homes")
        if not homes:
            raise YokisApiError("Aucune maison Yokis associée à ce compte")
        self.home_id = homes[0]["homeId"]

    async def async_get_equipments(self) -> list[dict[str, Any]]:
        return await self._async_request("GET", f"/homes/{self.home_id}/equipments")

    async def async_send_command(self, uuid: str, order: str) -> None:
        await self._async_request(
            "POST", f"/homes/{self.home_id}/equipments/{uuid}/command", json={"order": order}
        )

    async def _async_request(self, method: str, path: str, **kwargs) -> Any:
        if self._token is None:
            raise YokisApiError("Client non authentifié, appeler async_login() d'abord")

        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with self._session.request(
                method, f"{API_BASE_URL}{path}", headers=headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    # Token probablement expiré : on retente une fois après re-login.
                    await self.async_login()
                    headers = {"Authorization": f"Bearer {self._token}"}
                    async with self._session.request(
                        method, f"{API_BASE_URL}{path}", headers=headers, **kwargs
                    ) as retry_resp:
                        retry_resp.raise_for_status()
                        return await _read_json_or_none(retry_resp)
                resp.raise_for_status()
                return await _read_json_or_none(resp)
        except aiohttp.ClientError as err:
            raise YokisApiError(f"Erreur réseau ({method} {path}) : {err}") from err


async def _read_json_or_none(resp: aiohttp.ClientResponse) -> Any:
    # Les endpoints de commande renvoient un 200 avec un corps vide.
    text = await resp.text()
    return await resp.json() if text else None
