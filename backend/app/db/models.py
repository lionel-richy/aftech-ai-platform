"""Schéma PostgreSQL (SQLAlchemy 2.0, déclaratif) — DÉVELOPPEMENT LOCAL
UNIQUEMENT pour l'instant (voir docs/DATABASE.md). Jamais importé par
app/main.py ni par modal_app.py : cette couche est optionnelle et n'est pas
encore câblée dans l'application déployée.

Principe directeur : TOUTE table métier porte organization_id, indexé, avec
une contrainte de clé étrangère explicite vers organizations.id — jamais une
table "globale" implicite qui mélangerait les données de plusieurs
organisations (voir tests/test_db_isolation.py pour la preuve).

Suppression : "soft delete" (deleted_at) pour les entités qu'on veut pouvoir
restaurer (organizations, users, memberships, documents, conversations).
Les tables d'évènements/historique (messages, audit_events, model_requests,
evaluation_results, ingestion_jobs, document_versions) sont APPEND-ONLY :
pas de deleted_at, seulement une suppression en cascade si le parent est
vraiment supprimé (voir ondelete="CASCADE" sur chaque ForeignKey).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- Identité / organisation ---------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Pas de organization_id ICI : un utilisateur peut appartenir à plusieurs
    # organisations (voir memberships) — exactement comme GitHub/Slack.


class Role(Base):
    """Catalogue GLOBAL de rôles (4 lignes, voir migration 0001) — pas une
    table "métier" par organisation : c'est un référentiel partagé, comme un
    type énuméré mais modifiable sans migration. Reflète exactement les 4
    rôles déjà affichés (en démonstration) sur la page Administration."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)  # "org_admin", "ai_manager", ...
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Membership(Base):
    """Lien organisation <-> utilisateur <-> rôle. C'est CETTE table qui est
    "métier" et porte organization_id — pas Role ni User."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Assistant IA : conversations ------------------------------------------


class ResponseLanguage(str, enum.Enum):
    fr = "fr"
    en = "en"
    de = "de"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class AnswerStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_FOUND = "NOT_FOUND"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """APPEND-ONLY : une question ou une réponse ne se modifie jamais après
    coup (cohérent avec le principe anti-hallucination déjà en place côté
    RAG — on ne réécrit pas l'historique)."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Dénormalisé : permet de scoper/indexer directement par organisation
    # sans jointure sur conversations, et rend l'isolation multi-tenant
    # vérifiable même si une requête oublie de passer par conversation_id.
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    response_language: Mapped[ResponseLanguage | None] = mapped_column(
        Enum(ResponseLanguage, name="response_language"), nullable=True
    )
    status: Mapped[AnswerStatus | None] = mapped_column(Enum(AnswerStatus, name="answer_status"), nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validated_claims: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)


# --- Documents ---------------------------------------------------------


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    DELETING = "DELETING"


class Document(Base):
    """Identité STABLE d'un document déposé. L'historique de chaque
    traitement vit dans document_versions — cette table garde juste l'état
    COURANT (dénormalisé pour des lectures rapides, ex. la Bibliothèque)."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "hash_sha256", name="uq_document_org_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    nom_original: Mapped[str] = mapped_column(String(300), nullable=False)
    nom_stocke: Mapped[str] = mapped_column(String(100), nullable=False)
    taille_octets: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    statut: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), nullable=False)
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nb_passages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.created_at"
    )


class DocumentVersion(Base):
    """Historique APPEND-ONLY de chaque tentative de traitement d'un document
    (une ligne par passage UPLOADED -> ... -> READY/FAILED). Utile pour
    déboguer un échec d'extraction sans perdre la trace des tentatives
    précédentes."""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    statut: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), nullable=False)
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nb_passages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped["Document"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),)


class IngestionJobType(str, enum.Enum):
    upload_process = "upload_process"
    delete_reindex = "delete_reindex"
    full_reindex = "full_reindex"
    rollback = "rollback"


class IngestionJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IngestionJob(Base):
    """Trace APPEND-ONLY de chaque reconstruction d'index (voir
    index_builder.py) — aujourd'hui seulement visible dans les logs Modal,
    perdue au redémarrage du conteneur."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[IngestionJobType] = mapped_column(Enum(IngestionJobType, name="ingestion_job_type"), nullable=False)
    statut: Mapped[IngestionJobStatus] = mapped_column(
        Enum(IngestionJobStatus, name="ingestion_job_status"), nullable=False
    )
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Intégrations ---------------------------------------------------------


class IntegrationProvider(str, enum.Enum):
    jira = "jira"
    sharepoint = "sharepoint"
    onedrive = "onedrive"
    google_drive = "google_drive"
    local_folders = "local_folders"
    github = "github"
    gitlab = "gitlab"
    database = "database"


class IntegrationStatus(str, enum.Enum):
    not_connected = "not_connected"
    config_required = "config_required"
    connected = "connected"
    error = "error"


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_integration_org_provider"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider, name="integration_provider"), nullable=False
    )
    statut: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, name="integration_status"), nullable=False, default=IntegrationStatus.not_connected
    )
    # JAMAIS de secret ici (clé API, token...) — seulement des réglages non
    # sensibles (ex. URL d'un espace Jira). Les vrais secrets, s'ils arrivent
    # un jour, vivront dans un gestionnaire de secrets dédié, pas en base.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Audit / métriques / évaluation ---------------------------------------


class AuditEvent(Base):
    """APPEND-ONLY. Remplace à terme JOURNAL_AUDIT_DEMO (données fictives,
    frontend/app/administration/page.tsx)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)  # "document.uploaded", "question.asked"...
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_audit_events_org_created", "organization_id", "created_at"),)


class ModelRequest(Base):
    """APPEND-ONLY. Version DURABLE de ce que backend/app/metrics.py garde
    seulement en mémoire process (perdu à chaque redémarrage)."""

    __tablename__ = "model_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    response_language: Mapped[ResponseLanguage] = mapped_column(
        Enum(ResponseLanguage, name="response_language"), nullable=False
    )
    status: Mapped[AnswerStatus] = mapped_column(Enum(AnswerStatus, name="answer_status"), nullable=False)
    recherche_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    generation_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    total_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    tokens_entree: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_generes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_model_requests_org_created", "organization_id", "created_at"),)


class EvaluationResult(Base):
    """APPEND-ONLY. Détail par affirmation validée (ou non) d'une réponse —
    aujourd'hui renvoyé au client puis jamais conservé côté serveur."""

    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    model_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_requests.id", ondelete="CASCADE"), nullable=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    fichier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_presente: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preuve_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = _created_at()


# Tables "métier" portant organization_id — utilisé par les migrations pour
# activer Row-Level Security automatiquement sur toutes, sans en oublier une.
TENANT_SCOPED_TABLES = (
    "memberships",
    "conversations",
    "messages",
    "documents",
    "document_versions",
    "ingestion_jobs",
    "integrations",
    "audit_events",
    "model_requests",
    "evaluation_results",
)
