"""Vérifie que la fonction Modal `availability` (backend/app/modal_app.py) :
- s'exécute réellement sans erreur (comme test_modal_app_loads.py pour web()) ;
- répond 200 sur GET /availability ;
- n'importe JAMAIS app.main ni app.rag_engine — donc ne charge jamais
  Qwen/BGE-M3 et n'a aucune chance de toucher un GPU.

Contexte (voir docs/exchange avec l'utilisateur, "Partie 2") : le frontend
doit pouvoir sonder la disponibilité de l'API en boucle (toutes les 30 s)
SANS jamais réinitialiser le minuteur de scale-to-zero du conteneur GPU de
web(). Cette fonction existe justement pour ça — ce test prouve qu'elle est
bien isolée du moteur IA, pas seulement "sur le papier".

Ignoré si le paquet `modal` n'est pas installé (comme test_modal_app_loads.py)."""

import sys
from pathlib import Path

import pytest

modal = pytest.importorskip("modal")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _importer_modal_app():
    sys.path.insert(0, str(BACKEND_DIR))
    from modal.cli.import_refs import ImportRef, import_file_or_module

    ref = ImportRef(file_or_module="app/modal_app.py", object_path="", use_module_mode=False)
    return import_file_or_module(ref)


def test_availability_function_executes_and_returns_fastapi_app(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    module = _importer_modal_app()

    resultat = module.availability.local()

    from fastapi import FastAPI

    assert isinstance(resultat, FastAPI)


def test_availability_endpoint_returns_ok_status(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    module = _importer_modal_app()

    from fastapi.testclient import TestClient

    client = TestClient(module.availability.local())
    reponse = client.get("/availability")

    assert reponse.status_code == 200
    assert reponse.json()["status"] == "ok"


def test_availability_ne_touche_jamais_au_moteur_ia(monkeypatch):
    """Preuve que /availability est isolée du GPU : exécuter cette fonction
    ne doit JAMAIS importer app.main (où vit le lifespan qui charge
    Qwen/BGE-M3) ni app.rag_engine (le moteur lui-même)."""
    monkeypatch.chdir(BACKEND_DIR)
    for nom_module in ("app.main", "app.rag_engine"):
        sys.modules.pop(nom_module, None)

    module = _importer_modal_app()
    module.availability.local()

    assert "app.main" not in sys.modules
    assert "app.rag_engine" not in sys.modules


def test_availability_est_bien_separee_de_web_gpu():
    """web() (GPU) et availability() (CPU) doivent être deux fonctions Modal
    DISTINCTES — jamais la même, sans quoi les interroger l'une ou l'autre
    réinitialiserait le même minuteur de scale-to-zero."""
    module = _importer_modal_app()
    assert module.web is not module.availability


def test_decorateur_de_availability_ne_porte_aucune_configuration_gpu():
    """Lit le SOURCE de modal_app.py : le bloc @app.function(...) qui précède
    `def availability():` ne doit contenir aucun paramètre gpu=, contrairement
    à celui de web()."""
    source = (BACKEND_DIR / "app" / "modal_app.py").read_text(encoding="utf-8")
    avant_availability, _, apres = source.partition("def availability():")
    bloc_decorateur_availability = avant_availability.rsplit("@app.function(", 1)[-1]

    assert "gpu=" not in bloc_decorateur_availability
    # Et on vérifie que le test lui-même ne se trompe pas de fonction : le
    # bloc web() juste avant DOIT contenir gpu= (sinon web() a changé de
    # définition et ce test ne protège plus rien).
    avant_web, _, _ = source.partition("def web():")
    bloc_decorateur_web = avant_web.rsplit("@app.function(", 1)[-1]
    assert "gpu=" in bloc_decorateur_web
