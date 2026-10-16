DOMAIN = "yokis"

API_BASE_URL = "https://up.yokiscloud.fr/api/yno/v1"

# Valeurs de `deviceType` des modules de volets roulants (MVR). Seul
# YOKIS_UP_MVR (MVR500E-UP) a été testé sur un vrai appareil.
DEVICE_TYPE_YOKIS_V5_MVR = 3
DEVICE_TYPE_YOKIS_UP_MVR = 103
DEVICE_TYPE_ZIGBEE_MVR = 202
COVER_DEVICE_TYPES = {DEVICE_TYPE_YOKIS_V5_MVR, DEVICE_TYPE_YOKIS_UP_MVR, DEVICE_TYPE_ZIGBEE_MVR}
# L'ordre `liftPercentage` n'est pas proposé pour les MVR Zigbee génériques.
SET_POSITION_DEVICE_TYPES = {DEVICE_TYPE_YOKIS_V5_MVR, DEVICE_TYPE_YOKIS_UP_MVR}

# Délai maximal d'une requête vers l'API cloud (aiohttp attend 5 min par défaut)
REQUEST_TIMEOUT_SECONDS = 10

# Valeurs de `state.alive` d'un équipement
ALIVE_NOT_ALIVE = 1

# Valeurs de `eventType` des événements SSE `HOME_STATE`
HOME_EVENT_FULL_UPDATE = 0
HOME_EVENT_EQUIPMENTS_UPDATE = 1
HOME_EVENT_GATEWAY_OFFLINE = 7
HOME_EVENT_GATEWAY_ONLINE = 8

# Le serveur envoie un keep-alive toutes les 10 s sur le flux SSE : au-delà
# de ce délai sans rien recevoir, la connexion est considérée comme morte.
NOTIFS_READ_TIMEOUT_SECONDS = 30

# Attente avant reconnexion au flux SSE, doublée à chaque échec consécutif.
NOTIFS_RETRY_MIN_SECONDS = 5
NOTIFS_RETRY_MAX_SECONDS = 300
# Une connexion restée ouverte au moins aussi longtemps remet l'attente au minimum.
NOTIFS_STABLE_CONNECTION_SECONDS = 60
