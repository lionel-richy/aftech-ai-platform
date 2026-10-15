"""Moteur et sessions async SQLAlchemy — DÉVELOPPEMENT LOCAL UNIQUEMENT.

Jamais importé par app/main.py tant que cette couche n'est pas câblée dans
l'application déployée (voir docs/DATABASE.md). DATABASE_URL absente =
fonctionnalités DB simplement indisponibles, jamais un crash au démarrage.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

# IMPORTANT : "aftech_app" (pas "aftech", le propriétaire des tables) — en
# PostgreSQL, le propriétaire d'une table (et tout rôle BYPASSRLS) ignore
# purement et simplement les policies RLS. Seule une connexion avec un rôle
# restreint comme celui-ci fait réellement respecter l'isolation par
# organisation (voir migration 0001, qui crée ce rôle).
DATABASE_URL_DEFAUT = "postgresql+asyncpg://aftech_app:aftech-app-dev-local@localhost:5432/aftech"


def url_base_de_donnees() -> str:
    return os.environ.get("DATABASE_URL", DATABASE_URL_DEFAUT)


DATABASE_URL_ADMIN_DEFAUT = "postgresql+asyncpg://aftech:aftech-dev-local@localhost:5432/aftech"


def url_base_de_donnees_admin() -> str:
    return os.environ.get("DATABASE_URL_ADMIN", DATABASE_URL_ADMIN_DEFAUT)


_engine: AsyncEngine | None = None
_fabrique_session: async_sessionmaker[AsyncSession] | None = None
_engine_admin: AsyncEngine | None = None
_fabrique_session_admin: async_sessionmaker[AsyncSession] | None = None


def obtenir_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(url_base_de_donnees(), pool_pre_ping=True)
    return _engine


def obtenir_fabrique_session() -> async_sessionmaker[AsyncSession]:
    global _fabrique_session
    if _fabrique_session is None:
        _fabrique_session = async_sessionmaker(obtenir_engine(), expire_on_commit=False)
    return _fabrique_session


def _obtenir_engine_admin() -> AsyncEngine:
    global _engine_admin
    if _engine_admin is None:
        _engine_admin = create_async_engine(url_base_de_donnees_admin(), pool_pre_ping=True)
    return _engine_admin


def _obtenir_fabrique_session_admin() -> async_sessionmaker[AsyncSession]:
    global _fabrique_session_admin
    if _fabrique_session_admin is None:
        _fabrique_session_admin = async_sessionmaker(_obtenir_engine_admin(), expire_on_commit=False)
    return _fabrique_session_admin


@asynccontextmanager
async def session_pour_organisation(organization_id: str) -> AsyncIterator[AsyncSession]:
    """Ouvre une session avec le contexte RLS positionné pour CETTE
    organisation (voir migration 0001 : les policies lisent
    current_setting('app.current_org_id')). set_config(..., true) = portée
    locale à la transaction seulement, jamais fuité vers une autre requête
    qui réutiliserait la même connexion du pool."""
    fabrique = obtenir_fabrique_session()
    async with fabrique() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": organization_id})
            yield session


@asynccontextmanager
async def session_administrateur() -> AsyncIterator[AsyncSession]:
    """Connexion avec le rôle PROPRIÉTAIRE des tables ("aftech") : contourne
    délibérément les policies RLS — réservé aux scripts d'administration et
    aux tests qui doivent lire/écrire À TRAVERS plusieurs organisations.
    JAMAIS utilisé depuis une route HTTP normale (voir obtenir_fabrique_session,
    qui utilise le rôle restreint "aftech_app")."""
    fabrique = _obtenir_fabrique_session_admin()
    async with fabrique() as session:
        yield session


async def fermer_engine() -> None:
    global _engine, _fabrique_session, _engine_admin, _fabrique_session_admin
    if _engine is not None:
        await _engine.dispose()
    if _engine_admin is not None:
        await _engine_admin.dispose()
    _engine = None
    _fabrique_session = None
    _engine_admin = None
    _fabrique_session_admin = None
