"""Fixtures partagées par tests/test_db_*.py — PAS un conftest.py
(volontairement) : importé explicitement par chaque fichier, pour ne jamais
imposer de dépendance à Postgres aux tests existants (FakeRagEngine, etc.),
qui n'en ont pas besoin et doivent continuer à tourner sans Docker.

pytest.importorskip-style : si Postgres n'est pas joignable (Docker non
démarré), tous les tests de ces fichiers sont SKIP, pas FAILED — même
principe que pytest.importorskip("modal") dans test_modal_app_loads.py.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import fermer_engine, obtenir_engine, session_administrateur, session_pour_organisation


def postgres_est_joignable() -> bool:
    async def _verifier() -> bool:
        try:
            engine = obtenir_engine()
            async with engine.connect() as connexion:
                await connexion.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — n'importe quelle erreur = indisponible
            return False
        finally:
            await fermer_engine()

    return asyncio.run(_verifier())


requiert_postgres = pytest.mark.skipif(
    not postgres_est_joignable(),
    reason="PostgreSQL local indisponible (voir backend/docker-compose.yml : docker compose up -d)",
)


@pytest_asyncio.fixture
async def deux_organisations():
    """Crée 2 organisations réelles pour la durée du test, puis les
    supprime (cascade : efface aussi tout ce qui a été inséré dedans)."""
    async with session_administrateur() as session:
        from app.db.repositories import OrganizationRepository

        depot = OrganizationRepository(session)
        suffixe = uuid.uuid4().hex[:8]
        org_a = await depot.creer(f"Org Test A {suffixe}", f"org-test-a-{suffixe}")
        org_b = await depot.creer(f"Org Test B {suffixe}", f"org-test-b-{suffixe}")
        await session.commit()

    yield org_a, org_b

    async with session_administrateur() as session:
        await session.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a.id, "b": org_b.id})
        await session.commit()


def session_org(organization_id):
    return session_pour_organisation(str(organization_id))
