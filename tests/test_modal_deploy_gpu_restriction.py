"""Vérifie que backend/scripts/modal_deploy.sh refuse A100 (et toute valeur
inconnue) AVANT d'appeler `modal deploy` — aucun réseau, aucun paquet modal requis."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "modal_deploy.sh"


def _lancer(gpu_env: str | None):
    environnement = os.environ.copy()
    if gpu_env is None:
        environnement.pop("MODAL_GPU_TYPE", None)
    else:
        environnement["MODAL_GPU_TYPE"] = gpu_env
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=environnement,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_a100_refuse_avant_tout_appel_modal():
    resultat = _lancer("A100")
    assert resultat.returncode == 1
    assert "pas autorisé" in resultat.stdout
    assert "modal deploy" not in resultat.stdout  # jamais affiché la commande comme si on allait l'exécuter


def test_valeur_inconnue_refusee():
    resultat = _lancer("H100")
    assert resultat.returncode == 1


def test_t4_accepte_affiche_le_plan_sans_deployer():
    resultat = _lancer("T4")
    assert resultat.returncode == 0
    assert "GPU choisi          : T4" in resultat.stdout
    assert "Rien n'a été déployé." in resultat.stdout


def test_l4_est_le_defaut():
    resultat = _lancer(None)
    assert resultat.returncode == 0
    assert "GPU choisi          : L4" in resultat.stdout
