# Yokis (Yno UP cloud) — Home Assistant Integration

[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-custom__component-blue?style=flat-square&logo=home-assistant)](https://www.home-assistant.io)

Intégration Home Assistant pour piloter des modules Yokis **MVR500E-UP**
(volets roulants) connectés à une gateway **GATE-UP**, via l'API cloud non
officielle de la plateforme **Yno UP** — sans dongle Zigbee dédié sur Home
Assistant, et sans perdre le pilotage depuis l'app Yno UP.

> ⚠️ **Intégration non officielle.** Développée indépendamment par
> observation du protocole réseau de l'app Yno UP, à des fins
> d'interopérabilité. Aucune affiliation avec Yokis/Urmet. L'API n'étant pas
> documentée publiquement, elle peut changer sans préavis.

## Fonctionnalités

- Connexion via email/mot de passe du compte Yno UP (config flow, pas de YAML)
- Découverte automatique des volets du foyer
- Contrôle : ouvrir / fermer / stopper
- Rafraîchissement périodique de l'état (position en %, toutes les 60s)

### Limitation connue

Pas de positionnement précis (`set_cover_position`) : l'API Yokis ne remonte
la position qu'une fois le mouvement terminé (pas de télémétrie en temps
réel pendant le trajet), donc impossible d'interrompre un mouvement au bon
moment de manière fiable. Seuls open/close/stop sont exposés pour l'instant.

## Installation

Manuelle (pas encore publié sur HACS) :

1. Copier le dossier `custom_components/yokis/` dans
   `<config Home Assistant>/custom_components/`
2. Redémarrer Home Assistant
3. Réglages → Appareils et services → Ajouter une intégration → rechercher
   "Yokis"
4. Renseigner l'email et le mot de passe du compte Yno UP

## Développement

Le dossier `scripts/` contient un prototype Python autonome
(`yokis_prototype.py`) pour tester l'API cloud directement, hors Home
Assistant :

```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
cp scripts/.env.example scripts/.env   # renseigner YOKIS_EMAIL / YOKIS_PASSWORD

.venv/bin/python scripts/yokis_prototype.py list
.venv/bin/python scripts/yokis_prototype.py cmd <uuid> <open|close|stop>
```

## Licence

[MIT](LICENSE)
