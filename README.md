# Yokis (Yno UP cloud) — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/Jean-Mat/HA-GateUp-Yokis?style=flat-square)](https://github.com/Jean-Mat/HA-GateUp-Yokis/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/Jean-Mat/HA-GateUp-Yokis/tests.yml?label=tests&style=flat-square)](https://github.com/Jean-Mat/HA-GateUp-Yokis/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

Intégration Home Assistant pour piloter des volets roulants équipés de
modules Yokis **MVR500E-UP** et reliés à une passerelle **GATE-UP**, via
l'API cloud de la plateforme **Yno UP**. Aucun dongle Zigbee n'est
nécessaire côté Home Assistant, et les volets restent pilotables depuis
l'app Yno UP et les interrupteurs muraux.

> ⚠️ **Intégration non officielle**, développée indépendamment à des fins
> d'interopérabilité, sans aucune affiliation avec Yokis ou Urmet. L'API
> cloud Yno UP n'étant pas documentée publiquement, elle peut changer sans
> préavis et rendre l'intégration inopérante.

## Prérequis

- Une passerelle Yokis **GATE-UP** configurée avec l'app **Yno UP**
- Des modules de volets roulants Yokis appairés à cette passerelle
- L'email et le mot de passe du compte Yno UP
- Home Assistant **2026.10** ou plus récent

## Fonctionnalités

- Connexion via email/mot de passe du compte Yno UP (config flow, pas de YAML)
- Découverte automatique des volets du foyer (une entité `cover` par volet)
- Contrôle : ouvrir / fermer / stopper / **positionner en %**
- **Mise à jour de l'état en temps réel, sans polling** : l'intégration
  écoute le flux d'événements (SSE) de l'API Yokis. Les mouvements lancés
  depuis Home Assistant, l'app Yno UP ou l'**interrupteur mural** sont
  remontés en moins d'une seconde
- Reconnexion automatique du flux en cas de coupure, avec resynchronisation
  de l'état
- Volets marqués indisponibles quand la passerelle GATE-UP est hors ligne ou
  qu'un module ne répond plus
- Nouveau volet ajouté dans l'app Yno UP : il apparaît automatiquement dans
  Home Assistant, sans redémarrage
- Diagnostics téléchargeables (Appareils et services → Yokis → ⋮ →
  Télécharger les diagnostics), sans email, mot de passe ni adresse MAC
- Ré-authentification : si le mot de passe du compte Yno UP change, Home
  Assistant affiche une notification pour saisir le nouveau, sans avoir à
  supprimer l'intégration
- Interface traduite en français et en anglais, erreurs de commande
  affichées dans Home Assistant

### Comportement de la position

- Convention identique à Home Assistant : 0 % = fermé, 100 % = ouvert
- Pendant un mouvement, la position est remontée par étapes (environ toutes
  les 10 à 15 s), puis la position finale à l'arrêt du volet

## Installation

### Avec HACS (recommandé)

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Jean-Mat&repository=HA-GateUp-Yokis&category=integration)

Ou manuellement dans HACS :

1. HACS → menu ⋮ → **Dépôts personnalisés**
2. Ajouter `https://github.com/Jean-Mat/HA-GateUp-Yokis`, catégorie
   **Intégration**
3. Rechercher **Yokis** dans HACS, puis **Télécharger**
4. Redémarrer Home Assistant

### Manuelle

1. Télécharger la dernière
   [release](https://github.com/Jean-Mat/HA-GateUp-Yokis/releases)
2. Copier le dossier `custom_components/yokis/` dans
   `<config Home Assistant>/custom_components/`
3. Redémarrer Home Assistant

## Configuration

1. **Paramètres → Appareils et services → Ajouter une intégration**
2. Rechercher **Yokis**
3. Saisir l'email et le mot de passe du compte Yno UP

Les volets du compte apparaissent automatiquement, un appareil et une entité
`cover` par volet.

## Matériel testé et limites

- Testé avec des modules **MVR500E-UP** (Yokis UP). Les modules de volets
  Yokis V5 et Zigbee génériques sont reconnus d'après l'API mais n'ont pas
  été testés ; le positionnement en % n'est pas disponible pour les modules
  Zigbee génériques
- Seuls les volets roulants sont gérés (pas les éclairages, chauffage, etc.)
- Si le compte a accès à plusieurs maisons, seule la première est utilisée
- Fonctionnement 100 % cloud : une connexion internet est nécessaire, côté
  passerelle comme côté Home Assistant

## Dépannage

- **Logs détaillés** : Paramètres → Appareils et services → Yokis → ⋮ →
  **Activer la journalisation de débogage**
- **Diagnostics** : même menu → **Télécharger les diagnostics** (email, mot
  de passe et adresses MAC masqués) ; à joindre à un
  [ticket](https://github.com/Jean-Mat/HA-GateUp-Yokis/issues)

## Développement

Le dossier `scripts/` contient un prototype Python autonome
(`yokis_prototype.py`) pour tester l'API cloud directement, hors Home
Assistant :

```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
cp scripts/.env.example scripts/.env   # renseigner YOKIS_EMAIL / YOKIS_PASSWORD

.venv/bin/python scripts/yokis_prototype.py list                          # volets et position
.venv/bin/python scripts/yokis_prototype.py cmd <uuid> <open|close|stop>
.venv/bin/python scripts/yokis_prototype.py position <uuid> <0-100>
.venv/bin/python scripts/yokis_prototype.py listen                        # flux d'événements SSE
```

### Tests

Les tests automatisés (`tests/`) utilisent
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
et nécessitent Python 3.14, comme Home Assistant. Le script suivant lance
ruff puis les tests dans un conteneur Docker, sans rien installer sur la
machine :

```bash
scripts/run_tests.sh                       # tous les tests
scripts/run_tests.sh tests/test_cover.py   # arguments passés à pytest
```

Avec un environnement Python 3.14 :

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
pytest
```

Les tests tournent aussi automatiquement sur GitHub à chaque push.

## Licence

[MIT](LICENSE)
