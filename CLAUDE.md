# Projet AFTECH AI Platform

## Niveau de l'utilisateur

L'utilisateur apprend le développement et l'intelligence artificielle.
Explique chaque modification en français simple avant de l'appliquer.

## Organisation

- Le code source reste local.
- Les calculs GPU sont exécutés avec Google Colab CLI.
- Les scripts GPU sont placés dans `scripts/`.
- Les notebooks d'apprentissage sont placés dans `notebooks/`.
- Les résultats sont placés dans `results/`.
- Les données de test sont placées dans `data/samples/`.

## Sécurité

- Ne jamais utiliser de données réelles de clients.
- Ne jamais lire ou envoyer le fichier `.env`.
- Ne jamais écrire une clé API dans le code.
- Ne jamais téléverser automatiquement les données SharePoint ou Jira.
- Toujours demander confirmation avant de créer ou supprimer une ressource.
- Toujours arrêter une session Colab à la fin d'un test.

## Colab

- Utiliser une T4 par défaut.
- Vérifier le GPU avant de charger un modèle.
- Commencer par Qwen 4B en quantification 4 bits.
- Ne pas tenter Qwen 32B sur une T4.
- Enregistrer les mesures de VRAM dans `results/benchmarks/`.

## Qualité

- Ajouter des commentaires simples.
- Expliquer les erreurs.
- Créer de petites étapes vérifiables.
- Ne pas modifier plusieurs parties du projet en même temps.
