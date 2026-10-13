"""Fixtures pytest partagées.

Principe : on ne charge JAMAIS les vrais modèles dans les tests (trop lent,
dépend du réseau, demande un GPU pour la génération). On remplace le moteur
RAG par un double (`FakeRagEngine`) via `app.dependency_overrides`, ce qui
teste le comportement réel de l'API (routes, validation, codes HTTP, erreurs)
sans dépendre de Qwen/BGE-M3/FAISS.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Permet "import app.main" quand pytest est lancé depuis n'importe où.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("BACKEND_API_KEY", "test-key")

from app.main import app, get_engine  # noqa: E402
from app.metrics import metrics_store  # noqa: E402

API_KEY = os.environ["BACKEND_API_KEY"]


@pytest.fixture(autouse=True)
def _reset_metrics():
    """metrics_store est un singleton partagé par tout le process : on le
    remet à zéro avant chaque test pour qu'ils restent indépendants de
    l'ordre d'exécution."""
    metrics_store.reset()
    yield


class FakeRagEngine:
    """Double de test du moteur RAG : pas de modèle chargé, réponses figées."""

    def __init__(self, *, ready: bool = True, ask_result: dict | None = None, ask_exception: Exception | None = None):
        self.ready = ready
        self._ask_result = ask_result
        self._ask_exception = ask_exception

    def health(self) -> dict:
        return {
            "status": "ok" if self.ready else "degraded",
            "ready": self.ready,
            "llm_model": "Qwen/Qwen3-4B-Instruct-2507",
            "embedding_model": "BAAI/bge-m3",
            "gpu": "Tesla L4" if self.ready else "indisponible",
            "vram_totale_octets": 23_609_475_072 if self.ready else None,
            "vram_utilisee_octets": 3_240_000_000 if self.ready else None,
            "documents_count": 3,
            "chunks_count": 353,
        }

    def documents(self) -> list[dict]:
        return [
            {
                "nom_fichier": "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf",
                "pages": 15,
                "passages": 55,
                "hash_sha256": "deadbeef",
                "modele_embeddings": "BAAI/bge-m3",
                "date_index": "2026-09-29T17:40:06+00:00",
            }
        ]

    def ask(self, question: str, top_k: int = 8, response_language: str = "fr") -> dict:
        if self._ask_exception is not None:
            raise self._ask_exception
        return self._ask_result


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture
def make_client():
    """Fabrique un TestClient avec un FakeRagEngine injecté à la place du vrai moteur."""
    clients: list[TestClient] = []

    def _make(fake_engine: FakeRagEngine) -> TestClient:
        app.dependency_overrides[get_engine] = lambda: fake_engine
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make

    app.dependency_overrides.clear()
    for client in clients:
        client.close()
