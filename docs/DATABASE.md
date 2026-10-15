# Base de données PostgreSQL — AFTECH AI Platform

**Statut : développement local uniquement.** Rien ici n'est déployé sur
Modal, aucune donnée réelle de production n'y transite. Cette base est la
fondation d'une future persistance structurée, pas encore câblée dans
l'application qui tourne aujourd'hui (voir "Ce qui reste fictif" plus bas).

## 1. Démarrer en local

```bash
cd backend
docker compose up -d                       # démarre Postgres (port 5432)
pip install -r requirements-db.txt         # sqlalchemy, alembic, asyncpg, psycopg
DATABASE_URL_ADMIN="postgresql+psycopg://aftech:aftech-dev-local@localhost:5432/aftech" \
  python -m alembic upgrade head           # applique les migrations
python scripts/seed_postgres_from_existing_data.py   # importe les données de démo existantes
```

Arrêter : `docker compose down` (garde les données) ou `docker compose down -v` (efface tout).

## 2. Les 13 tables, expliquées simplement

| Table | À quoi elle sert |
|---|---|
| `organizations` | Une entreprise cliente. Tout le reste appartient à une organisation. |
| `users` | Une personne (peut appartenir à plusieurs organisations). |
| `roles` | Catalogue **global** des 4 rôles déjà affichés en démo (Administrateur, Responsable IA, Utilisateur, Auditeur) — pas lié à une organisation, comme un menu déroulant partagé. |
| `memberships` | Le lien "cette personne, dans cette organisation, a ce rôle". |
| `conversations` | Un fil de discussion avec l'Assistant IA. |
| `messages` | Chaque question/réponse d'une conversation (jamais modifié après coup). |
| `documents` | Un PDF déposé : état actuel (nom, statut, nombre de pages...). |
| `document_versions` | L'historique de CHAQUE tentative de traitement d'un document (utile pour déboguer un échec). |
| `ingestion_jobs` | Trace de chaque reconstruction d'index (aujourd'hui seulement dans les logs Modal, perdue au redémarrage). |
| `integrations` | État des connecteurs (Jira, SharePoint...) — jamais de secret stocké ici. |
| `audit_events` | Le vrai journal d'audit (remplace le tableau fictif de la page Administration). |
| `model_requests` | Chaque question posée à Qwen, de façon durable (remplace `metrics.py`, qui oublie tout au redémarrage). |
| `evaluation_results` | Le détail de chaque affirmation validée ou rejetée (aujourd'hui renvoyé au client puis jamais gardé). |

**Règle centrale** : toutes les tables "métier" (lignes ci-dessus sauf `organizations`, `users`, `roles`) ont une colonne `organization_id` obligatoire, et PostgreSQL lui-même (pas seulement le code) empêche de lire ou d'écrire les données d'une autre organisation — voir section 4.

## 3. Diagramme des relations

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ MEMBERSHIPS : a
    USERS ||--o{ MEMBERSHIPS : a
    ROLES ||--o{ MEMBERSHIPS : definit

    ORGANIZATIONS ||--o{ CONVERSATIONS : possede
    USERS ||--o{ CONVERSATIONS : demarre
    CONVERSATIONS ||--o{ MESSAGES : contient

    ORGANIZATIONS ||--o{ DOCUMENTS : possede
    DOCUMENTS ||--o{ DOCUMENT_VERSIONS : historique
    ORGANIZATIONS ||--o{ INGESTION_JOBS : lance
    DOCUMENTS ||--o{ INGESTION_JOBS : concerne

    ORGANIZATIONS ||--o{ INTEGRATIONS : configure
    ORGANIZATIONS ||--o{ AUDIT_EVENTS : journalise
    USERS ||--o{ AUDIT_EVENTS : agit

    ORGANIZATIONS ||--o{ MODEL_REQUESTS : mesure
    CONVERSATIONS ||--o{ MODEL_REQUESTS : genere
    MODEL_REQUESTS ||--o{ EVALUATION_RESULTS : detaille
```

## 4. Isolation multi-organisation (Row-Level Security)

Deux rôles PostgreSQL distincts, créés par la migration `0001_initial_schema` :

- **`aftech`** — propriétaire des tables, utilisé UNIQUEMENT par Alembic (migrations) et les scripts d'administration. Contourne volontairement l'isolation (`session_administrateur()`).
- **`aftech_app`** — rôle restreint, **sans** `BYPASSRLS`, utilisé par l'application au quotidien (`session_pour_organisation(org_id)`). PostgreSQL lui interdit, au niveau moteur, de voir ou modifier une ligne dont `organization_id` ne correspond pas à son contexte de session — **même si le code applicatif oublie un `WHERE organization_id = ...`**.

C'est volontaire et important : si on ne se fiait qu'au code pour filtrer par organisation, UN SEUL endroit oublié suffirait à faire fuir des données entre clients. Avec Row-Level Security, c'est la base de données elle-même qui refuse.

Preuve réelle (voir `backend/tests/test_db_isolation.py`, 5 tests, tous exécutés contre un vrai PostgreSQL) :
- une organisation ne voit pas les conversations d'une autre, même sans filtre écrit dans la requête ;
- impossible d'insérer une ligne au nom d'une autre organisation ;
- un document "supprimé en douceur" (soft delete) reste invisible aux autres organisations.

## 5. Suppression : politique

- **Soft delete** (`deleted_at`, restaurable) : `organizations`, `users`, `memberships`, `documents`, `conversations`.
- **Append-only, jamais supprimé par l'app** : `messages`, `audit_events`, `model_requests`, `evaluation_results`, `ingestion_jobs`, `document_versions` — un historique ne se réécrit pas.
- **Suppression définitive (RGPD, etc.)** : pas encore implémentée — nécessiterait une tâche de purge périodique, volontairement hors périmètre ici.

## 6. Migrations versionnées

Gérées par Alembic (`backend/alembic/`). La migration `0001_initial_schema` est générée depuis `app/db/models.py` (source de vérité du schéma), puis enrichie à la main pour le rôle restreint et les policies RLS.

```bash
# Créer une nouvelle migration après avoir modifié app/db/models.py :
python -m alembic revision --autogenerate -m "description du changement"
# L'appliquer :
python -m alembic upgrade head
# Revenir en arrière d'un cran :
python -m alembic downgrade -1
```

## 7. Sauvegarde et restauration (développement local)

```bash
# Sauvegarde (format personnalisé pg_dump, compressé) :
docker exec aftech-postgres-dev pg_dump -U aftech -Fc aftech > sauvegarde.dump

# Restauration dans une base VIDE :
docker exec -i aftech-postgres-dev pg_restore -U aftech -d aftech --clean --if-exists < sauvegarde.dump
```

Pour une vraie production future : sauvegardes automatiques + rétention gérées par l'hébergeur choisi (voir rapport de mission pour les options), jamais un simple `pg_dump` manuel.

## 8. Couche d'accès aux données

`backend/app/db/repositories.py` — une classe par domaine (`DocumentRepository`, `ConversationRepository`, `AuditRepository`, `ModelRequestRepository`, `RoleRepository`, `OrganizationRepository`), chacune recevant une session déjà ouverte avec le bon contexte d'organisation. Testée contre un vrai PostgreSQL dans `backend/tests/test_db_repositories.py`.

## 9. Ce qui reste fictif après cette étape

- **L'application déployée sur Modal continue de fonctionner exactement comme avant** : `data/indexes/aftech_documents/manifest.json` reste la source de vérité pour `/ask` et `/documents`, `metrics.py` reste en mémoire. Cette base de données n'est PAS encore branchée dans `main.py`.
- La page Administration du frontend affiche toujours ses tableaux codés en dur (`UTILISATEURS_DEMO`, etc.) — ils ont maintenant un équivalent réel en base (voir `scripts/seed_postgres_from_existing_data.py`), mais le frontend ne les lit pas encore depuis là.
- Pas d'authentification réelle : un seul utilisateur "Démo" existe dans toute l'app (`Topbar.tsx`), donc `user_id`/`organization_id` dans la base ne peuvent pas encore être remplis par de vraies sessions.
- Pas de facturation, pas de purge RGPD, pas de connecteur `integrations` réellement fonctionnel (délibérément hors périmètre).
