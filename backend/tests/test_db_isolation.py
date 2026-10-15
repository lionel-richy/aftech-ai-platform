"""Preuve qu'une organisation ne peut JAMAIS accéder aux données d'une
autre — exigence explicite. Les tests passent par le rôle applicatif
restreint "aftech_app" (jamais le rôle propriétaire "aftech", qui
contournerait Row-Level Security) : voir app/db/session.py.

Si PostgreSQL local n'est pas démarré (docker compose up -d), ces tests
sont SKIP, pas FAILED (voir db_fixtures.requiert_postgres)."""

import uuid

import pytest
from sqlalchemy import select, text

from app.db.models import Conversation, Document, MessageRole
from app.db.repositories import ConversationRepository, DocumentRepository, NouveauMessage
from db_fixtures import deux_organisations, requiert_postgres, session_org  # noqa: F401

pytestmark = requiert_postgres


@pytest.mark.asyncio
async def test_une_organisation_ne_voit_pas_les_conversations_dune_autre(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ConversationRepository(session)
        await depot.creer(org_a.id, title="Conversation privée A")

    async with session_org(org_b.id) as session:
        depot = ConversationRepository(session)
        await depot.creer(org_b.id, title="Conversation privée B")

    async with session_org(org_a.id) as session:
        resultat = await session.execute(select(Conversation))
        conversations = list(resultat.scalars())

    assert len(conversations) == 1
    assert conversations[0].title == "Conversation privée A"


@pytest.mark.asyncio
async def test_meme_sans_filtre_organization_id_dans_la_requete_rien_ne_fuit(deux_organisations):
    """Le test le plus important : AUCUN WHERE organization_id=... écrit à
    la main — c'est PostgreSQL (RLS) qui filtre, pas une discipline de code
    qu'on pourrait oublier d'appliquer dans une future route."""
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        await depot.creer(org_a.id, "a.pdf", "id-a.pdf", 100, "hash-a")

    async with session_org(org_b.id) as session:
        depot = DocumentRepository(session)
        await depot.creer(org_b.id, "b.pdf", "id-b.pdf", 100, "hash-b")

    async with session_org(org_b.id) as session:
        resultat = await session.execute(select(Document))  # PAS de .where(organization_id=...)
        documents = list(resultat.scalars())

    assert [d.nom_original for d in documents] == ["b.pdf"]


@pytest.mark.asyncio
async def test_impossible_dinserer_une_ligne_pour_une_autre_organisation(deux_organisations):
    """La policy WITH CHECK doit aussi bloquer une ÉCRITURE malveillante/
    buggée qui tenterait d'insérer une ligne au nom d'une autre organisation
    que celle du contexte de session courant."""
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        with pytest.raises(Exception, match="row-level security|new row violates"):
            await session.execute(
                text(
                    "INSERT INTO conversations (id, organization_id, title) "
                    "VALUES (:id, :org_id, 'injection malveillante')"
                ),
                {"id": uuid.uuid4(), "org_id": org_b.id},
            )
            await session.flush()


@pytest.mark.asyncio
async def test_les_messages_dune_conversation_restent_prives_a_lorganisation(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ConversationRepository(session)
        conversation_a = await depot.creer(org_a.id, title="Support A")
        await depot.ajouter_message(
            conversation_a, NouveauMessage(role=MessageRole.user, content="Question confidentielle de A")
        )

    async with session_org(org_b.id) as session:
        from app.db.models import Message

        resultat = await session.execute(select(Message))
        messages_visibles_par_b = list(resultat.scalars())

    assert messages_visibles_par_b == []


@pytest.mark.asyncio
async def test_suppression_douce_dun_document_najoute_pas_de_fuite(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        document = await depot.creer(org_a.id, "secret.pdf", "id-secret.pdf", 10, "hash-secret")
        await depot.marquer_supprime(document)

    async with session_org(org_b.id) as session:
        resultat = await session.execute(select(Document))
        assert list(resultat.scalars()) == []
