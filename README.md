# AFTECH AI Platform

Assistant documentaire RAG (*Retrieval-Augmented Generation*) avec vérification anti-hallucination intégrée : chaque affirmation générée doit être justifiée par une citation exacte, vérifiée mot pour mot dans le document source, puis confirmée par un second appel au modèle avant d'être présentée comme fiable.

## Fonctionnalités

- **Assistant IA** — pose une question, obtient une réponse **sourcée** (document, page, citation exacte) avec un statut `COMPLETE` / `PARTIAL` / `NOT_FOUND` selon ce qui a pu être réellement vérifié.
- **Trilingue (fr/en/de)** — l'interface et les réponses s'adaptent à la langue choisie ; les citations, elles, restent toujours dans la langue d'origine du document (jamais traduites).
- **Bibliothèque** — consultation des documents indexés, dépôt (upload) et suppression de PDF, avec suivi de statut (`UPLOADED → EXTRACTING → INDEXING → READY/FAILED`) et reconstruction atomique de l'index (jamais de remplacement direct — une version invalide ne remplace jamais une version qui fonctionnait).
- **Tableau de bord** — métriques réellement mesurées (latence, répartition des statuts, benchmark GPU comparatif T4/L4/A100), sans aucun chiffre inventé.
- **Administration / Intégrations** — préfigurent les futurs rôles, utilisateurs et connecteurs (Jira, SharePoint, GitHub…), clairement marqués comme démonstration tant qu'ils ne sont pas branchés sur de vraies données.

## Architecture

```
frontend/   Next.js 16 (App Router), Tailwind v4, next-intl
backend/    FastAPI + moteur RAG (FAISS + BGE-M3 pour la recherche, Qwen3-4B-Instruct-2507
            en 4 bits pour la génération), déployé sur Modal (GPU à la demande,
            scale-to-zero — aucun coût tant que personne n'utilise l'API)
scripts/    Outils Colab (benchmark GPU, construction d'index) indépendants du backend
docs/       Documentation technique (schéma de base de données, etc.)
```

**Mécanisme anti-hallucination** : pour chaque affirmation générée, le modèle doit fournir une citation exacte extraite du passage source. Cette citation est d'abord vérifiée **mot pour mot** (recherche de sous-chaîne, pas de confiance aveugle dans le modèle), puis un second appel — totalement indépendant, qui ne voit que la question, l'affirmation et la citation — doit confirmer que la citation prouve réellement l'affirmation. Une affirmation n'est acceptée que si les deux vérifications passent.

**Coûts maîtrisés** : le GPU (Modal) ne démarre qu'à la première vraie question et s'éteint automatiquement après 5 minutes d'inactivité. La surveillance de disponibilité tourne sur une fonction séparée, strictement CPU, pour ne jamais réveiller inutilement le GPU.

## Démarrage local

```bash
# Backend (nécessite un GPU pour la génération ; fonctionne en mode dégradé sans GPU)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Base de données PostgreSQL (fondation pour une future persistance structurée — voir [`docs/DATABASE.md`](docs/DATABASE.md)) :

```bash
cd backend
docker compose up -d
pip install -r requirements-db.txt
DATABASE_URL_ADMIN="postgresql+psycopg://aftech:aftech-dev-local@localhost:5432/aftech" python -m alembic upgrade head
```

## Tests

```bash
cd backend && pytest        # moteur RAG, API, pipeline documentaire, isolation PostgreSQL
cd frontend && npm test     # composants, routes, internationalisation
```

## État actuel

- **Backend** : déployé sur Modal, fonctionnel (assistant, bibliothèque, upload de documents).
- **Frontend** : fonctionnel en local, **pas encore hébergé publiquement**.
- **PostgreSQL** : schéma et migrations prêts, utilisés en développement local uniquement — pas encore connecté à l'application déployée.
- **Authentification** : pas encore implémentée (un seul profil de démonstration pour l'instant).

## Pile technique

Next.js 16 · TypeScript · Tailwind CSS v4 · FastAPI · Modal · FAISS · BGE-M3 · Qwen3-4B-Instruct · PostgreSQL · SQLAlchemy · Alembic
