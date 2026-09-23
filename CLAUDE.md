# Projet : Intégration Home Assistant custom pour Yokis

## Objectif

Créer une intégration Home Assistant (Python) permettant de piloter des modules
Yokis **MVR500E-UP** (micro-modules radio pour volets roulants, connectés en
Zigbee à une gateway Yokis) via l'API cloud de la gateway Yokis — sans passer
par un dongle Zigbee dédié sur Home Assistant.

Le but est de garder les modules appairés à la gateway Yokis existante
(pilotage possible depuis l'app Yno) tout en ajoutant un contrôle depuis
Home Assistant, en s'appuyant sur l'API HTTP que la gateway expose déjà.

## Contexte matériel

- Volets roulants électriques filaires, commande locale murale existante
- Modules **Yokis MVR500E-UP** (micro-module radio volet roulant, 2A/500VA,
  Zigbee 3.0) ajoutés en complément du câblage filaire
- Les modules communiquent en Zigbee avec une **gateway Yokis**, elle-même
  pilotée via l'app mobile **Yno**
- Home Assistant tourne sur un **Raspberry Pi 4** (Home Assistant OS)

## Point de départ technique : l'API Yokis

Il n'existe pas de documentation officielle publique de l'API cloud Yokis.
Cependant, un plugin Homebridge existant l'a déjà reverse-engineered :

- Dépôt : https://github.com/justarandomdev/homebridge-yokis-http-client
- Authentification : email + mot de passe du compte utilisé dans l'app **Yno**
  (ou un compte secondaire dédié)
- Le plugin est écrit en TypeScript/Node.js — c'est la meilleure base pour
  comprendre les endpoints HTTP, le format d'authentification et les requêtes
  de contrôle des appareils, avant d'écrire l'équivalent en Python

Prochaine étape immédiate : lire le code source du plugin (notamment
`src/platform.ts` et tout fichier type `src/yokisClient.ts` / `src/api.ts`)
pour en extraire :
- l'URL de base de l'API
- le mécanisme d'authentification (login → token ? session ?)
- l'endpoint de listing des appareils
- l'endpoint de contrôle (ouvrir/fermer/positionner un volet)

## Plan de développement

1. **Comprendre l'API Yokis** — analyser le code du plugin Homebridge
2. **Prototype Python autonome** (hors Home Assistant) — script simple qui
   s'authentifie, liste les appareils et pilote un volet, pour valider l'API
   avant de complexifier
3. **Structurer en intégration Home Assistant custom** — arborescence standard
   dans `custom_components/` :
   - `manifest.json`
   - `config_flow.py` (écran de configuration dans l'interface HA : email/mdp)
   - `cover.py` (plateforme exposant les volets comme entités `cover`)
4. **Généraliser à tous les appareils** — découverte automatique des modules
   du compte, polling régulier de l'état, gestion des erreurs (perte de
   connexion, expiration de token, etc.)
5. **Optionnel : packager et publier** — dépôt GitHub public, ajout comme
   dépôt personnalisé HACS (même approche que pour `daikin_onecta` et
   `ha-easycare-bywaterair`, déjà utilisés sur cette installation HA)

## Contexte du développeur

- Développeur expérimenté sur d'autres langages, **débutant en Python**
- Première intégration Home Assistant custom écrite de zéro
- Installation HA existante déjà fonctionnelle avec :
  - Climatisation Daikin via `daikin_onecta` (cloud, OAuth)
  - Piscine Waterair via `ha-easycare-bywaterair` (HACS)

## Points de vigilance identifiés

- Un appareil Zigbee ne peut être appairé qu'à un seul réseau à la fois —
  cette approche cloud évite justement ce problème puisqu'elle ne touche pas
  au réseau Zigbee existant de la gateway Yokis
- Bien vérifier les limites de rate-limiting éventuelles de l'API cloud Yokis
  (par analogie avec l'API Daikin qui impose des quotas stricts)
- Le plugin Homebridge de référence n'est pas officiellement documenté par
  Yokis : l'API peut changer sans préavis, prévoir une gestion d'erreur robuste