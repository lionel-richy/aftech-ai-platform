#!/bin/bash
# Lance le backend FastAPI en local, sur ce Mac.
#
# Important : ce Mac n'a pas de GPU CUDA, donc le moteur RAG démarrera en
# mode "degraded" (/health -> ready=false) : la recherche de documents et
# /health/ /documents / /metrics fonctionnent, mais /ask renverra une erreur
# 503 claire ("Backend indisponible") au lieu de planter. C'est le
# comportement attendu en local ; pour un vrai /ask fonctionnel, il faut
# déployer sur Modal (GPU).
set -e

cd "$(dirname "$0")/.."  # se placer dans backend/

if [ -f ../.env ]; then
    echo "Chargement des variables depuis .env..."
    set -a
    source ../.env
    set +a
fi

export INDEX_DIR="${INDEX_DIR:-../data/indexes/aftech_documents}"

echo "Démarrage du backend sur http://localhost:8000 (Ctrl+C pour arrêter)..."
python3 -m uvicorn app.main:app --reload --port 8000
