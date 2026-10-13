#!/bin/bash
# Lance l'assistant documentaire sur Colab, du début à la fin.
#
# Ce script existe parce que "colab exec -f script.py" n'envoie QUE le
# script lui-même : les fichiers de data/samples/ doivent être téléversés
# à la main à chaque nouvelle session, sinon le script les trouve vides.
#
# Utilisation : ./scripts/run_document_assistant.sh [nom_session]
set -e

SESSION="${1:-aftech-rag}"

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

# 3. Création du dossier distant puis envoi de chaque document, un par un
#    (colab upload ne gère qu'un fichier à la fois, pas un dossier entier)
echo "Préparation du dossier de données distant..."
echo "import os; os.makedirs('/content/data/samples', exist_ok=True)" | colab exec -s "$SESSION" --timeout 30

for fichier in data/samples/*.txt; do
    nom=$(basename "$fichier")
    echo "Envoi de $nom..."
    colab upload -s "$SESSION" "$fichier" "/content/data/samples/$nom"
done

# 4. Exécution du script principal (timeout large : téléchargement des modèles inclus)
echo "Lancement de l'assistant documentaire..."
colab exec -s "$SESSION" -f scripts/document_assistant.py --timeout 900

# 5. Rapatriement immédiat des résultats.
# Important : la VM Colab peut être recyclée par Google à tout moment après
# la fin du script (perte du fichier si on tarde à le télécharger à la main).
# On le télécharge donc tout de suite, dans la même commande.
echo "Téléchargement des résultats..."
mkdir -p results/benchmarks
colab download -s "$SESSION" /content/results/benchmarks/rag_test.json results/benchmarks/rag_test.json
echo "Résultats récupérés dans results/benchmarks/rag_test.json"
