from conftest import FakeRagEngine

CHAMPS_ATTENDUS = [
    "uptime_secondes",
    "requests_total",
    "status_complete",
    "status_partial",
    "status_not_found",
    "errors_total",
    "latence_moyenne_secondes",
]


def test_metrics_requires_api_key(make_client):
    client = make_client(FakeRagEngine())
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_has_expected_fields_and_no_fake_numbers(make_client, auth_headers):
    client = make_client(FakeRagEngine())
    resp = client.get("/metrics", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for champ in CHAMPS_ATTENDUS:
        assert champ in body

    # Aucune requête n'a encore été faite dans ce test : la latence moyenne
    # doit être absente (None), jamais un chiffre inventé.
    assert body["requests_total"] == 0
    assert body["latence_moyenne_secondes"] is None
