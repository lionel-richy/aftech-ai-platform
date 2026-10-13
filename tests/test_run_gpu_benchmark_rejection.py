"""Teste que scripts/run_gpu_benchmark.sh refuse un GPU inconnu AVANT tout
appel à Colab (donc ce test ne nécessite ni compte Colab ni réseau)."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_gpu_benchmark.sh"


def _lancer(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_refuse_h100():
    resultat = _lancer("H100")
    assert resultat.returncode == 1
    assert "inconnu" in resultat.stdout.lower() or "inconnu" in resultat.stderr.lower()


def test_refuse_g4():
    resultat = _lancer("G4")
    assert resultat.returncode == 1


def test_refuse_gpu_vide():
    resultat = _lancer()
    assert resultat.returncode == 1


def test_refuse_valeur_arbitraire():
    resultat = _lancer("pas-un-gpu")
    assert resultat.returncode == 1


def test_accepte_t4_l4_a100_dans_le_filtre_initial():
    """On ne va PAS jusqu'à l'appel Colab ici (pas de réseau dans les tests) :
    on vérifie seulement que T4/L4/A100 passent le premier filtre, en coupant
    l'exécution juste après via une commande 'colab' factice absente du PATH
    (donc la suite échouera proprement, mais PAS sur le contrôle de nom)."""
    for gpu in ("T4", "L4", "A100"):
        resultat = subprocess.run(
            ["bash", str(SCRIPT), gpu],
            capture_output=True,
            text=True,
            timeout=15,
            env={"PATH": "/usr/bin:/bin"},  # "colab" indisponible intentionnellement
            input="non\n",  # au cas où le prompt de confirmation A100 apparaîtrait
        )
        assert "GPU inconnu" not in resultat.stdout
