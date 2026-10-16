#!/bin/sh
# Lance les tests (et ruff) dans un conteneur Python 3.14, la version utilisée
# par Home Assistant : pas besoin d'installer ce Python sur la machine.
#
# Usage (depuis la racine du projet) :
#   scripts/run_tests.sh                      # tous les tests
#   scripts/run_tests.sh tests/test_cover.py  # arguments passés à pytest
#
# Les dépendances sont installées une fois dans le volume Docker
# `ha-gateup-yokis-venv`, puis réinstallées si requirements_test.txt change.
set -e
cd "$(dirname "$0")/.."

docker run --rm \
    -v ha-gateup-yokis-venv:/venv \
    -v "$PWD":/src -w /src \
    -e PYTHONDONTWRITEBYTECODE=1 \
    python:3.14-slim sh -c '
        if ! cmp -s requirements_test.txt /venv/requirements_test.txt; then
            echo "Installation des dépendances de test..."
            rm -rf /venv/py
            python -m venv /venv/py
            /venv/py/bin/pip install -q -r requirements_test.txt
            cp requirements_test.txt /venv/requirements_test.txt
        fi
        /venv/py/bin/ruff check --no-cache custom_components tests
        /venv/py/bin/pytest -p no:cacheprovider "$@"
    ' -- "$@"
