"""Démonstration concrète du "remplacement progressif" demandé : importe,
dans PostgreSQL local (voir docker-compose.yml), les données qui vivent
aujourd'hui dans des fichiers JSON ou codées en dur côté frontend.

NE remplace PAS encore le comportement de l'application déployée (qui
continue de lire data/indexes/aftech_documents/manifest.json et les
tableaux de frontend/app/administration/page.tsx, inchangés) — ce script
prouve seulement que les données PEUVENT migrer vers la base, avec les
mêmes contraintes/isolation que n'importe quelle autre ligne.

Idempotent : peut être relancé sans dupliquer les lignes déjà importées.

Usage (Postgres local démarré, voir backend/docker-compose.yml) :
    cd backend && python scripts/seed_postgres_from_existing_data.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import AuditEvent, Document, DocumentStatus, Membership, Organization, Role, User  # noqa: E402
from app.db.session import session_administrateur  # noqa: E402
from sqlalchemy import select  # noqa: E402

RACINE_PROJET = Path(__file__).resolve().parents[2]
MANIFEST_INDEX = RACINE_PROJET / "data" / "indexes" / "aftech_documents" / "manifest.json"

# Reflète EXACTEMENT frontend/app/administration/page.tsx (UTILISATEURS_DEMO,
# JOURNAL_AUDIT_DEMO) — migré tel quel, pas inventé. Toujours labellisé comme
# tel dans audit_events.event_metadata (jamais présenté comme une activité réelle).
UTILISATEURS_DEMO = [
    ("a.dubois@aftech.example", "A. Dubois", "org_admin"),
    ("m.nguyen@aftech.example", "M. Nguyen", "ai_manager"),
    ("s.okafor@aftech.example", "S. Okafor", "user"),
    ("j.moreau@aftech.example", "J. Moreau", "auditor"),
]

JOURNAL_AUDIT_DEMO = [
    ("login.demo", "a.dubois@aftech.example"),
    ("library.viewed", "s.okafor@aftech.example"),
    ("question.asked", "m.nguyen@aftech.example"),
]


async def principal() -> None:
    async with session_administrateur() as session:
        resultat = await session.execute(select(Organization).where(Organization.slug == "aftech"))
        organisation = resultat.scalar_one_or_none()
        if organisation is None:
            organisation = Organization(name="AFTECH", slug="aftech")
            session.add(organisation)
            await session.flush()
            print(f"Organisation créée : {organisation.id}")
        else:
            print(f"Organisation déjà présente : {organisation.id}")

        resultat = await session.execute(select(Role))
        roles_par_cle = {r.key: r for r in resultat.scalars()}

        utilisateurs_par_email: dict[str, User] = {}
        for email, nom, cle_role in UTILISATEURS_DEMO:
            resultat = await session.execute(select(User).where(User.email == email))
            utilisateur = resultat.scalar_one_or_none()
            if utilisateur is None:
                utilisateur = User(email=email, display_name=nom)
                session.add(utilisateur)
                await session.flush()
            utilisateurs_par_email[email] = utilisateur

            resultat = await session.execute(
                select(Membership).where(
                    Membership.organization_id == organisation.id, Membership.user_id == utilisateur.id
                )
            )
            if resultat.scalar_one_or_none() is None:
                session.add(
                    Membership(organization_id=organisation.id, user_id=utilisateur.id, role_id=roles_par_cle[cle_role].id)
                )

        if MANIFEST_INDEX.is_file():
            manifest = json.loads(MANIFEST_INDEX.read_text(encoding="utf-8"))
            stats = manifest.get("stats_par_pdf", {})
            hashes = manifest.get("hashes_pdf", {})
            for nom_fichier in manifest.get("pdf", []):
                hash_sha256 = hashes.get(nom_fichier, "")
                resultat = await session.execute(
                    select(Document).where(Document.organization_id == organisation.id, Document.hash_sha256 == hash_sha256)
                )
                if resultat.scalar_one_or_none() is not None:
                    continue
                infos = stats.get(nom_fichier, {})
                session.add(
                    Document(
                        organization_id=organisation.id,
                        nom_original=nom_fichier,
                        nom_stocke=nom_fichier,  # historique : pas de nom_stocke interne généré
                        taille_octets=0,  # inconnu : le PDF d'origine n'est pas sur ce volume
                        hash_sha256=hash_sha256 or f"historique-{nom_fichier}",
                        statut=DocumentStatus.READY,
                        nb_pages=infos.get("pages", 0),
                        nb_passages=infos.get("passages", 0),
                    )
                )
                print(f"Document historique importé : {nom_fichier}")
        else:
            print(f"Pas de manifest à {MANIFEST_INDEX} (rien à importer pour les documents).")

        resultat = await session.execute(select(AuditEvent).where(AuditEvent.organization_id == organisation.id))
        deja_importe = resultat.first() is not None
        if deja_importe:
            print("Journal d'audit déjà importé (ignoré, script idempotent).")
        else:
            for event_type, email in JOURNAL_AUDIT_DEMO:
                session.add(
                    AuditEvent(
                        organization_id=organisation.id,
                        actor_user_id=utilisateurs_par_email[email].id,
                        event_type=event_type,
                        event_metadata={"source": "migré depuis JOURNAL_AUDIT_DEMO (frontend, données de démonstration)"},
                    )
                )

        await session.commit()
        print("Import terminé.")


if __name__ == "__main__":
    asyncio.run(principal())
