# Projet : Intégration Home Assistant custom pour Yokis

## Objectif

Intégration Home Assistant (Python) permettant de piloter des modules Yokis
**MVR500E-UP** (micro-modules radio pour volets roulants, Zigbee 3.0) appairés
à une gateway Yokis **GATE-UP**, via l'API cloud de la plateforme **Yno UP** —
sans dongle Zigbee dédié sur Home Assistant.

Les modules restent appairés à la gateway Yokis (pilotage toujours possible
depuis l'app Yno UP) ; Home Assistant passe par l'API HTTP cloud.

## Matériel de test

- Volets roulants électriques filaires, commande locale murale existante
- Modules **Yokis MVR500E-UP** (2A/500VA, Zigbee 3.0) ajoutés en complément du
  câblage filaire
- Gateway **Yokis GATE-UP**, pilotée via l'app mobile **Yno UP**
- Home Assistant OS

## API Yokis (non officielle)

API cloud de la plateforme Yno UP, non documentée publiquement. Tout ce qui
suit a été vérifié par des appels réels.

- URL de base : `https://up.yokiscloud.fr/api/yno/v1`
- `POST /auth/signin` avec `{"login": email, "password": mdp}` → `{"token": ...}`
  (400/401 = identifiants refusés)
- Les appels suivants utilisent `Authorization: Bearer <token>` ; un 401
  signifie token expiré → re-login
- `GET /homes` → liste de maisons (`homeId`) ; seule la première est utilisée
- `GET /homes/{homeId}` → `{"accessType": 0, "online": true}` : `online` =
  passerelle connectée au cloud
- `GET /homes/{homeId}/equipments` → liste d'équipements : `uuid`, `name`,
  `deviceType`, `state.percentage`,
  `informations.{manufacturerName, modelIdentifier, softVersion}`
- `deviceType` des volets (MVR) : 3 = Yokis V5, 103 = Yokis UP (MVR500E-UP,
  seul testé), 202 = Zigbee générique (pas d'ordre `liftPercentage`)
- `POST /homes/{homeId}/equipments/{uuid}/command` avec `{"order": ...}` →
  200, corps vide
- Ordres valides pour les volets : `open`, `close`, `stop`
  (`up`/`down`/`lift_up`/`lift_down`/`on`/`off` sont rejetés)
- Positionnement : `{"order": "liftPercentage", "params": {"liftPercentage": N}}`
  (N de 0 à 100)
- Sens du `percentage` vérifié sur un volet réel : 0 = fermé, 100 = ouvert
  (même convention que Home Assistant, aucune inversion)
- `GET /homes/{homeId}/notifs` → flux **SSE** (`text/event-stream`) des
  changements d'état, y compris les mouvements faits à l'interrupteur mural :
  - `data:{"type":"EQUIPMENT_STATE","state":{"uuid":...,"percentage":...,"alive":2,...}}`
  - `HOME_STATE` : `{"type":"HOME_STATE","eventType":7}` (observé en réel) ;
    0/1 = données à recharger, 7 = passerelle hors ligne, 8 = en ligne. Au
    retour en ligne, la passerelle renvoie un `EQUIPMENT_STATE` par volet
  - autres types : `EQUIPMENT_ADD`, `ERROR` ;
    `ROOM_STATE` / `TCM_STATE` reçus aussi, ignorés
  - une commande envoyée juste après la coupure de la passerelle (avant
    l'événement 7) finit en timeout plutôt qu'en 410 `GATEWAY_OFFLINE`
  - `state.alive` d'un équipement : 0 = inconnu, 1 = injoignable, 2 = joignable
  - keep-alive (commentaire `:`) toutes les 10 s, `retry:2000`
  - une position intermédiaire environ toutes les 14 s pendant le trajet,
    puis la position finale ; `GET /equipments` ne donne que la position
    au repos

## Architecture du code

- `custom_components/yokis/`
  - `api.py` — client `aiohttp` asynchrone (`YokisApiClient`), exceptions
    `YokisApiError` / `YokisAuthError`, re-login automatique (une fois,
    sous verrou) sur 401
  - `coordinator.py` — `DataUpdateCoordinator`, données indexées par `uuid` :
    mises à jour en temps réel par le flux SSE (tâche de fond avec
    reconnexion et attente progressive), aucun polling ; liste complète
    rechargée seulement au démarrage, après une reconnexion du flux ou sur
    événement `EQUIPMENT_ADD` / `HOME_STATE` ; suit l'état en ligne de la
    passerelle (`gateway_online`)
  - `cover.py` — une entité `cover` (shutter) par équipement dont le
    `deviceType` est un module de volet (MVR) ; open/close/stop/set_position ;
    indisponible si la passerelle est hors ligne ou le module injoignable ;
    `has_entity_name` + `name = None` : l'entité prend le nom de l'appareil
    (donc `self.name` vaut None, utiliser le nom de l'équipement) ; les
    volets ajoutés dans Yno UP sont créés à la volée (écouteur sur le
    coordinateur), sans recharger l'intégration
  - `diagnostics.py` — export des diagnostics (email, mot de passe, adresses
    MAC masqués)
  - `config_flow.py` — saisie email/mot de passe, unique_id = email en
    minuscules ; ré-authentification (nouveau mot de passe)
  - `const.py` — URL, délais des requêtes et du flux SSE
  - `manifest.json`, `strings.json`
- `scripts/yokis_prototype.py` — prototype synchrone (`requests`) hors HA,
  identifiants dans `scripts/.env` (ignoré par git, ne jamais le lire)
- `tests/` — tests `pytest-homeassistant-custom-component` :
  - `test_api.py` : client HTTP contre un faux serveur Yokis local (aiohttp,
    127.0.0.1, fixture `socket_enabled`)
  - `test_config_flow.py`, `test_init.py`, `test_cover.py` : vrai Home
    Assistant, client API simulé (`mock_api`) ; flux SSE simulé par
    `FakeNotifs` (`await fake_notifs.push(hass, événement)`)
- `scripts/run_tests.sh` — ruff + pytest dans un conteneur Docker Python 3.14
  (Python de la machine de dev : 3.10, trop ancien pour HA)
- CI GitHub : `hassfest` + validation HACS + tests/ruff (`tests.yml`)

## État d'avancement

1. ~~Comprendre l'API Yokis~~ — fait
2. ~~Prototype Python autonome~~ — fait (`scripts/yokis_prototype.py`)
3. ~~Intégration HA custom~~ — fonctionnelle (config flow, covers, flux SSE)
4. ~~Fiabilisation~~ — fait (voir problèmes connus ci-dessous)
5. **Publication HACS** — en cours (dépôt personnalisé HACS, releases GitHub)

## Problèmes connus / à corriger

Bugs :
1. ~~Burst de rafraîchissement inefficace~~ — supprimé, remplacé par le flux
   SSE `/notifs`
2. ~~Traductions absentes~~ — corrigé (`translations/en.json` + `fr.json`,
   `strings.json` en anglais comme source)
3. ~~Récursion infinie possible au re-login~~ — corrigé (seul `/auth/signin`
   est rejoué, une seule fois ; `retry_on_401=False` pendant la connexion)
4. ~~`TimeoutError` non capturée, pas de timeout explicite~~ — corrigé
   (`REQUEST_TIMEOUT_SECONDS` = 10 s dans `const.py`, capturée dans `api.py`)
5. ~~Erreurs API non converties en `HomeAssistantError`~~ — corrigé
   (`_async_send_command` dans `cover.py`)
6. ~~`KeyError` si un équipement disparaît du compte~~ — corrigé
   (`available` + `.get()` dans `cover.py`)
7. ~~`manifest.json` incomplet, hassfest en échec~~ — corrigé (vérifié en
   local avec l'image Docker `ghcr.io/home-assistant/hassfest`)

Robustesse / bonnes pratiques HA :
- ~~Pas de flux de ré-authentification~~ — fait (`ConfigEntryAuthFailed` au
  setup et dans le coordinateur, `async_start_reauth` depuis le flux SSE et
  les commandes, étape `reauth_confirm` dans `config_flow.py`)
- ~~Re-logins concurrents possibles~~ — protégés par un `asyncio.Lock`
- ~~`KeyError` non encapsulées sur `data["token"]` / `homes[0]["homeId"]`~~
  — converties en `YokisApiError`
- Une seule maison gérée (`homes[0]`)
- ~~Détection des volets par `percentage is not None` fragile~~ — détection
  par `deviceType` (3, 103, 202), positionnement réservé aux types 3 et 103
- ~~Migrer `hass.data[DOMAIN]` vers `entry.runtime_data`~~ — fait
  (`YokisConfigEntry` dans `coordinator.py`)
- ~~Aucun test~~ — fait (`tests/`, lancés par `scripts/run_tests.sh` et en CI)

## Points de vigilance

- Un appareil Zigbee ne peut être appairé qu'à un seul réseau à la fois —
  l'approche cloud évite ce problème
- Rate-limiting de l'API cloud inconnu : rester raisonnable sur la fréquence
  de reconnexion au flux SSE
- API non documentée : elle peut changer sans préavis, gestion d'erreur
  robuste indispensable
