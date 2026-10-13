from conftest import FakeRagEngine


def test_availability_returns_ok_without_api_key(make_client):
    # ready=False : prouve que /availability répond quand même "ok" — elle
    # ne dépend PAS de l'état du moteur IA (Qwen/BGE-M3), contrairement à
    # /health. Pas de header Authorization non plus : aucune information
    # sensible n'est renvoyée.
    client = make_client(FakeRagEngine(ready=False))
    resp = client.get("/availability")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_availability_does_not_call_engine_ask_or_health(make_client, monkeypatch):
    """/availability ne doit JAMAIS lire l'état du moteur — elle ne doit même
    pas appeler engine.health()."""
    engine = FakeRagEngine(ready=True)
    appels = []
    health_original = engine.health
    engine.health = lambda: (appels.append("health") or health_original())  # noqa: E731

    client = make_client(engine)
    client.get("/availability")

    assert appels == []
