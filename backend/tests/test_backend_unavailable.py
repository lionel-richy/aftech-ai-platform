"""Scénario explicitement demandé : backend indisponible (pas de GPU, modèle
non chargé...). L'API doit répondre clairement (503), jamais planter ni
renvoyer de traceback."""

from app.rag_engine import BackendUnavailable
from conftest import FakeRagEngine


def test_ask_returns_503_when_backend_unavailable(make_client, auth_headers):
    client = make_client(
        FakeRagEngine(ready=False, ask_exception=BackendUnavailable("Aucun GPU CUDA détecté."))
    )

    resp = client.post("/ask", json={"question": "Bonjour ?"}, headers=auth_headers)

    assert resp.status_code == 503
    body = resp.json()
    assert "indisponible" in body["detail"].lower()
    assert "Traceback" not in body["detail"]


def test_chat_completions_returns_503_when_backend_unavailable(make_client, auth_headers):
    client = make_client(
        FakeRagEngine(ready=False, ask_exception=BackendUnavailable("Aucun GPU CUDA détecté."))
    )

    resp = client.post(
        "/v1/chat/completions",
        json={"model": "aftech-qwen3-4b", "messages": [{"role": "user", "content": "Bonjour ?"}]},
        headers=auth_headers,
    )

    assert resp.status_code == 503


def test_health_still_responds_when_backend_unavailable(make_client):
    client = make_client(FakeRagEngine(ready=False))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ready"] is False


def test_unexpected_exception_never_leaks_traceback(make_client, auth_headers):
    client = make_client(FakeRagEngine(ready=True, ask_exception=RuntimeError("boom interne imprévu")))

    resp = client.post("/ask", json={"question": "Bonjour ?"}, headers=auth_headers)

    assert resp.status_code == 500
    body = resp.json()
    assert "boom interne imprévu" not in body["detail"]
    assert "request_id=" in body["detail"]
