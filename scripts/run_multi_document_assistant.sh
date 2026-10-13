#!/bin/bash
# Lance l'assistant documentaire multi-PDF sur Colab, du début à la fin :
# session -> dépendances -> PDF -> index (construit ou réutilisé) -> questions
# de test -> rapatriement de l'index et des résultats sur le Mac.
#
# Comme pour les autres scripts run_*.sh : "colab exec -f script.py" n'envoie
# QUE le script lui-même, donc les PDF (et l'index local s'il existe déjà)
# doivent être téléversés à la main.
#
# Utilisation : ./scripts/run_multi_document_assistant.sh [nom_session]
set -e

SESSION="${1:-aftech-documents}"

DOSSIER_PDF_LOCAL="data/documents"
DOSSIER_INDEX_LOCAL="data/indexes/aftech_documents"
DOSSIER_INDEX_REMOTE="/content/data/indexes/aftech_documents"
ARCHIVE_LOCALE="/tmp/aftech_documents.tar.gz"

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

# 3. Compression puis envoi des PDF vers Colab
# (colab upload ne gère qu'un fichier à la fois, pas un dossier entier)
echo "Compression de $DOSSIER_PDF_LOCAL..."
tar -czf "$ARCHIVE_LOCALE" -C data documents

echo "Envoi de l'archive PDF..."
colab upload -s "$SESSION" "$ARCHIVE_LOCALE" /content/aftech_documents.tar.gz

echo "Extraction de l'archive sur la machine distante..."
echo "import tarfile, os; os.makedirs('/content/data', exist_ok=True); tarfile.open('/content/aftech_documents.tar.gz').extractall('/content/data', filter='data')" \
    | colab exec -s "$SESSION" --timeout 60

rm -f "$ARCHIVE_LOCALE"

# 4. Envoi de l'index local, s'il existe déjà, pour tenter une réutilisation
# (build_document_index.py comparera les hash des PDF pour décider s'il faut
# reconstruire ou non).
if [ -f "$DOSSIER_INDEX_LOCAL/manifest.json" ]; then
    echo "Index local trouvé, envoi vers Colab pour tenter une réutilisation..."
    echo "import os; os.makedirs('$DOSSIER_INDEX_REMOTE', exist_ok=True)" | colab exec -s "$SESSION" --timeout 30
    for fichier in index.faiss chunks.json manifest.json; do
        if [ -f "$DOSSIER_INDEX_LOCAL/$fichier" ]; then
            colab upload -s "$SESSION" "$DOSSIER_INDEX_LOCAL/$fichier" "$DOSSIER_INDEX_REMOTE/$fichier"
        fi
    done
else
    echo "Aucun index local existant : il sera construit à partir de zéro."
fi

# 5. Construction (ou réutilisation, si les PDF n'ont pas changé) de l'index
echo "Construction/réutilisation de l'index..."
colab exec -s "$SESSION" -f scripts/build_document_index.py --timeout 1800

# 6. Questions de test sur l'index multi-PDF
echo "Lancement des questions de test..."
colab exec -s "$SESSION" -f scripts/query_document_index.py --timeout 1800

# 7. Rapatriement immédiat de l'index et des résultats.
# Important : la VM Colab peut être recyclée par Google à tout moment après
# la fin du script (perte des fichiers si on tarde à les télécharger à la main).
echo "Téléchargement de l'index et des résultats..."
mkdir -p "$DOSSIER_INDEX_LOCAL" results/benchmarks
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/index.faiss" "$DOSSIER_INDEX_LOCAL/index.faiss"
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/chunks.json" "$DOSSIER_INDEX_LOCAL/chunks.json"
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/manifest.json" "$DOSSIER_INDEX_LOCAL/manifest.json"
colab download -s "$SESSION" /content/results/benchmarks/multi_document_test.json results/benchmarks/multi_document_test.json

echo "Terminé : index dans $DOSSIER_INDEX_LOCAL/, résultats dans results/benchmarks/multi_document_test.json"
