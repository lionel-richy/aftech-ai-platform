#!/bin/bash
# Arrête définitivement l'app Modal (termine aussi les conteneurs en cours).
set -e

echo "Ceci va arrêter DÉFINITIVEMENT l'app 'aftech-ai-platform' sur Modal."
read -r -p "Confirmer l'arrêt ? (tapez 'oui' pour continuer) " reponse

if [ "$reponse" == "oui" ]; then
    modal app stop aftech-ai-platform
else
    echo "Annulé."
fi
