#!/bin/bash
# Lance le benchmark GPU reproductible (UN SEUL GPU à la fois) sur Colab.
#
# Usage : ./scripts/run_gpu_benchmark.sh <T4|L4|A100>
#
# Règles de sécurité appliquées (voir le cahier des charges) :
# - un seul GPU accepté par exécution, jamais H100/G4/autre ;
# - refuse de démarrer si une AUTRE session "aftech-benchmark-*" est déjà active ;
# - ne réessaie jamais automatiquement une allocation échouée ;
# - ne remplace jamais le GPU demandé par un autre ;
# - confirmation obligatoire avant A100 ;
# - la session est arrêtée même en cas d'erreur (trap) ;
# - la consommation Colab (`colab usage`) est capturée avant/après si possible.
set -u  # (pas "set -e" global : on veut contrôler nous-mêmes chaque échec pour le trap/l'arrêt propre)

GPU="${1:-}"

case "$GPU" in
    T4|L4|A100)
        ;;
    *)
        echo "Erreur : GPU inconnu ou non supporté à cette étape : '${GPU}'."
        echo "Valeurs acceptées : T4, L4, A100 (H100 et G4 ne sont pas proposés ici)."
        echo "Usage : $0 <T4|L4|A100>"
        exit 1
        ;;
esac

GPU_MINUSCULE=$(echo "$GPU" | tr '[:upper:]' '[:lower:]')
SESSION="aftech-benchmark-${GPU_MINUSCULE}"

RESULTS_DIR="results/benchmarks/gpu"
OUTPUT_REMOTE="/content/${GPU}.json"
OUTPUT_LOCAL="${RESULTS_DIR}/${GPU}.json"
CONFIG_LOCAL="/tmp/benchmark_config_${GPU_MINUSCULE}.json"
CONFIG_REMOTE="/content/benchmark_config.json"
INSTALL_TIMING_LOCAL="/tmp/install_timing_${GPU_MINUSCULE}.json"
INSTALL_TIMING_REMOTE="/content/install_timing.json"

mkdir -p "$RESULTS_DIR"

echo "== Benchmark GPU : $GPU (session '$SESSION') =="

# --- Confirmation obligatoire avant A100 (le plus coûteux des trois) ---
if [ "$GPU" == "A100" ]; then
    echo "Vous allez provisionner un GPU A100 — nettement plus coûteux qu'un T4/L4."
    read -r -p "Confirmer ? (tapez 'oui' pour continuer) " confirmation
    if [ "$confirmation" != "oui" ]; then
        echo "Annulé."
        exit 0
    fi
fi

# --- Vérifie qu'aucune AUTRE session de benchmark n'est déjà active ---
# (exigence : un seul GPU de benchmark à la fois)
AUTRES_SESSIONS=$(colab sessions 2>&1 | grep -i "aftech-benchmark-" | grep -v "$SESSION" || true)
if [ -n "$AUTRES_SESSIONS" ]; then
    echo "Erreur : une autre session de benchmark semble déjà active :"
    echo "$AUTRES_SESSIONS"
    echo "Arrêtez-la d'abord (colab stop -s <nom>) avant de lancer un nouveau GPU."
    exit 1
fi

# --- Consommation Colab avant (si la commande est disponible localement) ---
if command -v colab >/dev/null 2>&1 && colab usage >/dev/null 2>&1; then
    colab usage > "${RESULTS_DIR}/${GPU}_usage_avant.txt" 2>&1
    echo "Consommation Colab AVANT (voir ${RESULTS_DIR}/${GPU}_usage_avant.txt) :"
    cat "${RESULTS_DIR}/${GPU}_usage_avant.txt"
else
    echo "'colab usage' indisponible ici : copiez-la manuellement si besoin (voir docs/MODAL_COST_SAFETY.md)."
fi

# --- Nettoyage garanti, même en cas d'erreur ---
SESSION_CREEE=0
trap '
    if [ "$SESSION_CREEE" == "1" ]; then
        echo "Arrêt de la session $SESSION (trap)..."
        colab stop -s "$SESSION" >/dev/null 2>&1 || true
    fi
    if command -v colab >/dev/null 2>&1 && colab usage >/dev/null 2>&1; then
        colab usage > "'"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt" 2>&1
        echo "Consommation Colab APRÈS (voir '"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt) :"
        cat "'"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt"
    fi
' EXIT

# --- Création de la session (UNE seule tentative : pas de retry, pas de repli sur un autre GPU) ---
STATUT=$(colab status -s "$SESSION" 2>&1 || true)
if echo "$STATUT" | grep -qi "not found"; then
    echo "Création de la session GPU $GPU..."
    if ! colab --auth oauth2 new -s "$SESSION" --gpu "$GPU"; then
        echo "Erreur : allocation du GPU $GPU impossible (quota, indisponibilité...)."
        echo "Pas de nouvelle tentative automatique, et AUCUN autre GPU n'est utilisé à la place."
        exit 1
    fi
    SESSION_CREEE=1
else
    echo "Session déjà active, réutilisation."
    SESSION_CREEE=1
fi

# --- Installation des dépendances (mesurée si possible) ---
echo "Installation des dépendances (requirements-colab.txt)..."
DEBUT_INSTALL=$(date +%s)
if ! colab install -s "$SESSION" -r requirements-colab.txt; then
    echo "Erreur lors de l'installation des dépendances."
    exit 1
fi
FIN_INSTALL=$(date +%s)
echo "{\"temps_installation_secondes\": $((FIN_INSTALL - DEBUT_INSTALL))}" > "$INSTALL_TIMING_LOCAL"

# --- Envoi UNIQUEMENT des fichiers nécessaires (pas tout le projet) ---
# rag_engine.py est autonome (n'importe pas schemas/security/metrics/main) :
# seuls __init__.py et rag_engine.py sont requis côté "app".
echo "Envoi des fichiers nécessaires..."
echo "import os; os.makedirs('/content/backend/app', exist_ok=True); os.makedirs('/content/data/indexes/aftech_documents', exist_ok=True)" \
    | colab exec -s "$SESSION" --timeout 30

colab upload -s "$SESSION" backend/app/__init__.py /content/backend/app/__init__.py
colab upload -s "$SESSION" backend/app/rag_engine.py /content/backend/app/rag_engine.py
colab upload -s "$SESSION" data/indexes/aftech_documents/index.faiss /content/data/indexes/aftech_documents/index.faiss
colab upload -s "$SESSION" data/indexes/aftech_documents/chunks.json /content/data/indexes/aftech_documents/chunks.json
colab upload -s "$SESSION" data/indexes/aftech_documents/manifest.json /content/data/indexes/aftech_documents/manifest.json

cat > "$CONFIG_LOCAL" <<EOF
{
  "gpu_attendu": "$GPU",
  "output": "$OUTPUT_REMOTE",
  "index_dir": "/content/data/indexes/aftech_documents",
  "repetitions": 3,
  "seed": 42,
  "install_timing_file": "$INSTALL_TIMING_REMOTE"
}
EOF
colab upload -s "$SESSION" "$CONFIG_LOCAL" "$CONFIG_REMOTE"
colab upload -s "$SESSION" "$INSTALL_TIMING_LOCAL" "$INSTALL_TIMING_REMOTE"

# --- Validation du GPU + exécution du benchmark ---
# (gpu_benchmark.py revérifie lui-même torch.cuda.get_device_name(0) contre
# gpu_attendu et s'arrête AVANT d'écrire quoi que ce soit si ça ne correspond pas)
echo "Lancement du benchmark (peut prendre plusieurs minutes : chargement de Qwen + 6 questions x 3 répétitions)..."
if ! colab exec -s "$SESSION" -f scripts/gpu_benchmark.py --timeout 1800; then
    echo "ERREUR : le benchmark a échoué ou a été interrompu. Voir la sortie ci-dessus."
    exit 1
fi

# --- Téléchargement immédiat du résultat (la VM peut être recyclée à tout moment) ---
# Important : "colab exec" peut renvoyer un code de succès même si le script
# Python distant a planté (déjà observé). On NE FAIT DONC JAMAIS confiance au
# seul code de sortie : le fichier téléchargé est explicitement vérifié
# ci-dessous (présent, non vide, JSON valide) avant d'afficher "Terminé".
echo "Téléchargement du résultat..."
if ! colab download -s "$SESSION" "$OUTPUT_REMOTE" "$OUTPUT_LOCAL"; then
    echo "ERREUR : le téléchargement de $OUTPUT_REMOTE a échoué."
    exit 1
fi

if [ ! -s "$OUTPUT_LOCAL" ]; then
    echo "ERREUR : $OUTPUT_LOCAL est absent ou vide après téléchargement."
    exit 1
fi

ERREUR_JSON="/tmp/erreur_json_${GPU_MINUSCULE}.txt"
if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$OUTPUT_LOCAL" 2>"$ERREUR_JSON"; then
    echo "ERREUR : $OUTPUT_LOCAL ne contient pas du JSON valide :"
    cat "$ERREUR_JSON"
    rm -f "$ERREUR_JSON"
    exit 1
fi
rm -f "$ERREUR_JSON"

echo "Terminé : résultat valide (JSON) dans $OUTPUT_LOCAL"
# Le "trap" ci-dessus arrête la session et capture la consommation après,
# dans tous les cas (succès ou exit 1 sur l'une des erreurs ci-dessus).
