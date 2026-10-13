#!/bin/bash
# Affiche (puis suit) les logs de l'app déployée sur Modal.
set -e
modal app logs aftech-ai-platform
