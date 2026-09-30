DOMAIN = "yokis"

API_BASE_URL = "https://up.yokiscloud.fr/api/yno/v1"

# Fréquence de rafraîchissement de l'état des volets (cloud_polling)
UPDATE_INTERVAL_SECONDS = 60

# Après une commande (open/close/stop), la position remontée par la
# passerelle Yokis ne se stabilise qu'une fois le mouvement terminé — on
# rafraîchit donc plus fréquemment pendant une courte fenêtre pour que
# l'interface (icônes activées/grisées) se mette à jour sans attendre le
# prochain cycle de 60s.
FAST_POLL_INTERVAL_SECONDS = 3
FAST_POLL_DURATION_SECONDS = 15
