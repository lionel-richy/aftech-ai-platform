#!/bin/bash
# Déploiement Modal — SANS EXÉCUTION AUTOMATIQUE.
#
# Par défaut, ce script affiche le GPU choisi, le coût théorique, les
# paramètres d'arrêt, les secrets nécessaires et la commande exacte, mais ne
# déploie RIEN. Il faut relancer avec --yes pour déployer réellement.
set -e

GPU_TYPE="${MODAL_GPU_TYPE:-L4}"
SCALEDOWN=300
MAX_CONTAINERS=1
MIN_CONTAINERS=0

# Même règle que backend/app/gpu_config.py : A100 est explicitement interdit
# pour Qwen 4B (benchmark réel : aucun gain vs L4, coût plus élevé). On le
# vérifie ICI aussi, pour échouer avant même d'essayer modal deploy.
case "$GPU_TYPE" in
    T4|L4)
        ;;
    *)
        echo "ERREUR : MODAL_GPU_TYPE='$GPU_TYPE' n'est pas autorisé."
        echo "Valeurs acceptées : T4, L4. A100 est explicitement interdit pour Qwen 4B"
        echo "(benchmark réel : aucun gain vs L4, coût plus élevé — voir results/benchmarks/gpu/recommendation.md)."
        exit 1
        ;;
esac

cat <<EOF
=== Déploiement Modal — aftech-ai-platform ===

GPU choisi          : $GPU_TYPE (recommandé : L4 — quasi aussi rapide que A100 pour Qwen 4B, moins coûteux ; T4 = profil économique)
Conteneurs min/max   : $MIN_CONTAINERS / $MAX_CONTAINERS (scale-to-zero, jamais plus d'un conteneur GPU à la fois)
Arrêt automatique    : $SCALEDOWN secondes d'inactivité avant extinction du conteneur
Secret requis        : aftech-backend-secrets (doit contenir BACKEND_API_KEY)
                        -> à créer une seule fois, AVANT de déployer :
                           modal secret create aftech-backend-secrets BACKEND_API_KEY=<votre-clé>

Coût théorique (estimation — vérifiez le tarif exact sur modal.com/pricing
au moment du déploiement, les prix peuvent changer) :
  - 0 \$ tant qu'aucune requête n'arrive (min_containers=0, pas de conteneur
    qui tourne en permanence).
  - Facturé uniquement pendant qu'un conteneur GPU $GPU_TYPE est actif : du
    premier appel jusqu'à $SCALEDOWN secondes après le dernier appel reçu.
  - max_containers=$MAX_CONTAINERS : un seul conteneur GPU à la fois, donc la
    facture ne peut pas s'emballer même si plusieurs requêtes arrivent en
    même temps (elles attendront leur tour plutôt que d'ouvrir un 2e GPU).

Commande exacte qui sera exécutée :
  cd backend && modal deploy app/modal_app.py

EOF

if [ "$1" == "--yes" ]; then
    echo "Déploiement confirmé (--yes) : exécution..."
    cd "$(dirname "$0")/.."
    modal deploy app/modal_app.py
else
    echo "Rien n'a été déployé."
    echo "Pour déployer réellement : ./backend/scripts/modal_deploy.sh --yes"
fi
