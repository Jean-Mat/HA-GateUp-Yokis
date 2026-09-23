"""Prototype autonome pour l'API cloud Yokis "Yno UP" (hors Home Assistant).

API interne de l'app officielle (up.yokiscloud.fr/api/yno/v1), découverte par
analyse statique de la bibliothèque Flutter/Dart de l'app (pas de MITM).

Usage (depuis la racine du projet) :
    .venv/bin/python scripts/yokis_prototype.py list
    .venv/bin/python scripts/yokis_prototype.py cmd <uuid> <open|close|stop>
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://up.yokiscloud.fr/api/yno/v1"

# Valeurs de `order` confirmées pour les volets roulants (MVR500E-UP) :
#   open, close, stop
# (up/down/lift_up/lift_down/on/off sont rejetés par l'API pour ce type d'appareil)


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

    def send_command(self, uuid: str, order: str):
        url = f"{BASE_URL}/homes/{self.home_id}/equipments/{uuid}/command"
        r = self.session.post(url, json={"order": order})
        r.raise_for_status()
        return r


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


def cmd_send(uuid: str, order: str):
    client = build_client()
    client.login()
    r = client.send_command(uuid, order)
    print("status:", r.status_code)


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
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
