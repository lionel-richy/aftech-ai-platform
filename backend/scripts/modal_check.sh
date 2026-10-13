#!/bin/bash
# Vérifie que la CLI Modal est installée et authentifiée, sans rien déployer.
set -e

echo "== Profil Modal actif =="
modal profile current

echo ""
echo "== Apps Modal (en cours, déployées, récemment arrêtées) =="
modal app list
