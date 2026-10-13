#!/bin/bash
# Lance l'assistant documentaire PDF sur Colab, du début à la fin.
#
# Comme pour run_document_assistant.sh : "colab exec -f script.py" n'envoie
# QUE le script lui-même, donc le PDF doit être téléversé à la main à
# chaque nouvelle session, sinon le script ne le trouve pas.
#
# Utilisation : ./scripts/run_pdf_assistant.sh [nom_session]
set -e

SESSION="${1:-aftech-pdf}"
PDF_LOCAL="data/sample_pdf/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"
PDF_REMOTE="/content/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"

echo "== Session Colab : $SESSION =="

# 1. On vérifie si la session existe déjà ; sinon on en crée une nouvelle (T4 par défaut)
# Remarque : "colab status" renvoie toujours le code de sortie 0, même quand la
# session n'existe pas (bug connu de la version 0.6.0) — on regarde donc le texte
# du message plutôt que le code de sortie.
STATUT=$(colab status -s "$SESSION" 2>&1 || true)
if echo "$STATUT" | grep -qi "not found"; then
    echo "Session absente, création d'une nouvelle session GPU T4..."
    colab --auth oauth2 new -s "$SESSION" --gpu T4
else
    echo "Session déjà active, réutilisation."
fi

# 2. Installation des dépendances Python sur la machine distante
echo "Installation des dépendances (requirements-colab.txt)..."
colab install -s "$SESSION" -r requirements-colab.txt

# 3. Envoi du PDF vers /content (emplacement attendu par scripts/pdf_assistant.py)
echo "Envoi du PDF..."
colab upload -s "$SESSION" "$PDF_LOCAL" "$PDF_REMOTE"

# 4. Exécution du script principal (timeout large : téléchargement des modèles inclus)
echo "Lancement de l'assistant documentaire PDF..."
colab exec -s "$SESSION" -f scripts/pdf_assistant.py --timeout 900

# 5. Rapatriement immédiat des résultats.
# Important : la VM Colab peut être recyclée par Google à tout moment après
# la fin du script (perte du fichier si on tarde à le télécharger à la main).
# On le télécharge donc tout de suite, dans la même commande.
echo "Téléchargement des résultats..."
mkdir -p results/benchmarks
colab download -s "$SESSION" /content/results/benchmarks/pdf_rag_test.json results/benchmarks/pdf_rag_test.json
echo "Résultats récupérés dans results/benchmarks/pdf_rag_test.json"
