#!/bin/bash
# Vérifie qu'AUCUN conteneur GPU ne tourne actuellement (donc aucun coût en cours).
set -e

echo "== Conteneurs actuellement en cours d'exécution sur Modal =="
SORTIE=$(modal container list 2>&1)
echo "$SORTIE"

echo ""
if echo "$SORTIE" | grep -qi "aftech-ai-platform"; then
    echo "ATTENTION : au moins un conteneur de 'aftech-ai-platform' semble actif."
    echo "Un conteneur GPU actif est facturé. Utilisez modal_stop.sh si besoin."
else
    echo "OK : aucun conteneur 'aftech-ai-platform' actif — aucun coût GPU en cours."
fi
