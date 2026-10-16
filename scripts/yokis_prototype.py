"""Prototype autonome pour l'API cloud Yokis "Yno UP" (hors Home Assistant).

API cloud de la plateforme Yno UP (up.yokiscloud.fr/api/yno/v1), non
documentée publiquement.

Usage (depuis la racine du projet) :
    .venv/bin/python scripts/yokis_prototype.py list
    .venv/bin/python scripts/yokis_prototype.py cmd <uuid> <open|close|stop>
    .venv/bin/python scripts/yokis_prototype.py position <uuid> <0-100>
    .venv/bin/python scripts/yokis_prototype.py listen
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://up.yokiscloud.fr/api/yno/v1"

# Valeurs de `order` confirmées pour les volets roulants (MVR500E-UP) :
#   open, close, stop
# (up/down/lift_up/lift_down/on/off sont rejetés par l'API pour ce type d'appareil)
#
# Positionnement :
#   {"order": "liftPercentage", "params": {"liftPercentage": <int>}}
# Sens du pourcentage (0 = ouvert ou fermé ?) à confirmer par un essai réel.


class YokisClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.home_id = None

    def login(self):
        r = self.session.post(f"{BASE_URL}/auth/signin", json={"login": self.email, "password": self.password})
        r.raise_for_status()
        token = r.json()["token"]
        self.session.headers["Authorization"] = f"Bearer {token}"

        homes = self.session.get(f"{BASE_URL}/homes").json()
        self.home_id = homes[0]["homeId"]

    def list_equipments(self):
        r = self.session.get(f"{BASE_URL}/homes/{self.home_id}/equipments")
        r.raise_for_status()
        return r.json()

    def send_command(self, uuid: str, order: str, params: dict | None = None):
        url = f"{BASE_URL}/homes/{self.home_id}/equipments/{uuid}/command"
        body = {"order": order}
        if params is not None:
            body["params"] = params
        r = self.session.post(url, json=body)
        r.raise_for_status()
        return r

    def listen_notifs(self):
        """Flux SSE des notifications de la maison : renvoie chaque ligne brute reçue."""
        url = f"{BASE_URL}/homes/{self.home_id}/notifs"
        with self.session.get(url, stream=True, headers={"Accept": "text/event-stream"}, timeout=(10, None)) as r:
            print("status:", r.status_code, "| content-type:", r.headers.get("Content-Type"))
            r.raise_for_status()
            # chunk_size=1 : sans ça, requests attend 512 octets avant de rendre une ligne.
            for line in r.iter_lines(chunk_size=1, decode_unicode=True):
                yield line


def build_client() -> YokisClient:
    load_dotenv(Path(__file__).parent / ".env")
    email = os.environ.get("YOKIS_EMAIL")
    password = os.environ.get("YOKIS_PASSWORD")
    if not email or not password:
        sys.exit("YOKIS_EMAIL / YOKIS_PASSWORD manquants : copie .env.example en .env et remplis-le.")
    return YokisClient(email, password)


def cmd_list():
    client = build_client()
    client.login()
    equipments = client.list_equipments()

    print(f"{'uuid':<38} {'modèle':<14} {'%':<5} name")
    for e in equipments:
        model = e["informations"].get("modelIdentifier", "?")
        pct = e["state"].get("percentage", "?")
        print(f"{e['uuid']:<38} {model:<14} {pct:<5} {e['name']}")


def cmd_send(uuid: str, order: str, params: dict | None = None):
    client = build_client()
    client.login()
    r = client.send_command(uuid, order, params)
    print("status:", r.status_code)
    if r.text:
        print("réponse:", r.text)


def cmd_listen():
    client = build_client()
    client.login()
    print("Écoute des notifications (Ctrl+C pour arrêter)...")
    try:
        for line in client.listen_notifs():
            print(f"[{datetime.now():%H:%M:%S}] {line!r}", flush=True)
    except KeyboardInterrupt:
        pass


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    action = sys.argv[1]
    if action == "list":
        cmd_list()
    elif action == "cmd":
        if len(sys.argv) != 4:
            sys.exit("Usage: python scripts/yokis_prototype.py cmd <uuid> <open|close|stop>")
        cmd_send(sys.argv[2], sys.argv[3])
    elif action == "position":
        if len(sys.argv) != 4 or not sys.argv[3].isdigit() or not 0 <= int(sys.argv[3]) <= 100:
            sys.exit("Usage: python scripts/yokis_prototype.py position <uuid> <0-100>")
        cmd_send(sys.argv[2], "liftPercentage", {"liftPercentage": int(sys.argv[3])})
    elif action == "listen":
        cmd_listen()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
