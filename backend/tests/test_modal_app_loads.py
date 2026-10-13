"""Vérifie que backend/app/modal_app.py non seulement SE CHARGE, mais que le
corps de la fonction web() S'EXÉCUTE réellement sans erreur.

Bug réel rencontré : un `import os` manquant ne causait AUCUNE erreur au
chargement du module (seul `GPU_TYPE = resoudre_gpu_type()` s'exécute à ce
moment) — le NameError n'apparaissait qu'à l'exécution de web(), donc une
fois déployé sur Modal. Ce test appelle `.local()` pour exécuter vraiment le
corps de la fonction, comme Modal le ferait dans le conteneur.

Ignoré si le paquet `modal` n'est pas installé (pas une dépendance du venv
de test léger utilisé pour le reste de la suite).
"""

import sys
from pathlib import Path

import pytest

modal = pytest.importorskip("modal")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_web_function_executes_without_nameerror(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    from modal.cli.import_refs import ImportRef, import_file_or_module

    ref = ImportRef(file_or_module="app/modal_app.py", object_path="", use_module_mode=False)
    module = import_file_or_module(ref)

    resultat = module.web.local()

    # web() doit renvoyer la vraie app FastAPI (pas planter avant d'y arriver).
    from fastapi import FastAPI

    assert isinstance(resultat, FastAPI)
