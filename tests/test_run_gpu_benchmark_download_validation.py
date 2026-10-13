"""Teste la validation du téléchargement dans scripts/run_gpu_benchmark.sh :
le script ne doit JAMAIS afficher "Terminé" si colab exec a menti sur son
succès (bug réellement rencontré : NameError côté Python, mais colab exec
renvoie quand même un code de sortie 0), si le téléchargement échoue, si le
fichier est vide, ou si son contenu n'est pas du JSON valide.

Ces tests n'ont besoin NI d'un vrai compte Colab NI du reste du projet : un
faux exécutable "colab" (placé en tête de PATH) simule chaque sous-commande,
et le script tourne dans un dossier temporaire isolé.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT_REEL = Path(__file__).resolve().parents[1] / "scripts" / "run_gpu_benchmark.sh"

FAUX_COLAB = r"""#!/bin/bash
# Faux CLI "colab" pour les tests : simule chaque sous-commande utilisée par
# run_gpu_benchmark.sh, sans aucun accès réseau.

# Dernier argument (portable, pas besoin de bash >= 4.3 pour l'indexation négative)
for DERNIER_ARG in "$@"; do :; done

case "$*" in
  *"status -s"*)
    echo "not found"
    exit 0
    ;;
  *"sessions"*)
    exit 0
    ;;
  *"usage"*)
    exit 1
    ;;
  *"new -s"*)
    echo "Session READY."
    exit 0
    ;;
  *"install -s"*)
    exit 0
    ;;
  *"upload "*)
    exit 0
    ;;
  *"exec -s"*"-f scripts/gpu_benchmark.py"*)
    # Simule exactement le bug rapporté : le script Python distant a planté
    # (NameError), mais "colab exec" renvoie quand même un succès.
    exit 0
    ;;
  *"exec -s"*)
    cat >/dev/null  # consomme l'entrée (commande mkdir envoyée via un pipe)
    exit 0
    ;;
  *"download -s"*)
    case "$FAKE_DOWNLOAD_MODE" in
      fail)
        exit 1
        ;;
      empty)
        : > "$DERNIER_ARG"
        exit 0
        ;;
      invalid_json)
        echo "ceci n'est pas du JSON" > "$DERNIER_ARG"
        exit 0
        ;;
      *)
        echo '{"configuration": {"gpu_demande": "T4"}}' > "$DERNIER_ARG"
        exit 0
        ;;
    esac
    ;;
  *"stop -s"*)
    echo "stop appelé" >> "$COLAB_STUB_STOP_LOG"
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""


@pytest.fixture
def environnement_test(tmp_path):
    """Dossier de travail isolé + faux "colab" en tête de PATH."""
    dossier_bin = tmp_path / "fakebin"
    dossier_bin.mkdir()
    chemin_colab = dossier_bin / "colab"
    chemin_colab.write_text(FAUX_COLAB, encoding="utf-8")
    chemin_colab.chmod(chemin_colab.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    journal_stop = tmp_path / "stop.log"

    environnement = os.environ.copy()
    environnement["PATH"] = f"{dossier_bin}:{environnement['PATH']}"
    environnement["COLAB_STUB_STOP_LOG"] = str(journal_stop)

    return tmp_path, environnement, journal_stop


def lancer_script(tmp_path, environnement, mode_telechargement):
    environnement = {**environnement, "FAKE_DOWNLOAD_MODE": mode_telechargement}
    return subprocess.run(
        ["bash", str(SCRIPT_REEL), "T4"],
        cwd=tmp_path,
        env=environnement,
        capture_output=True,
        text=True,
        timeout=30,
        input="oui\n",  # au cas où une confirmation serait demandée
    )


class TestValidationTelechargement:
    def test_succes_affiche_termine_et_fichier_valide(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "success")

        assert resultat.returncode == 0
        assert "Terminé" in resultat.stdout
        fichier = tmp_path / "results" / "benchmarks" / "gpu" / "T4.json"
        assert fichier.is_file()
        assert fichier.stat().st_size > 0
        assert journal_stop.read_text() == "stop appelé\n"  # trap a bien arrêté la session

    def test_telechargement_echoue_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "fail")

        assert resultat.returncode != 0
        assert "Terminé" not in resultat.stdout
        assert "ERREUR" in resultat.stdout
        assert journal_stop.read_text() == "stop appelé\n"  # trap s'exécute même en échec

    def test_fichier_vide_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "empty")

        assert resultat.returncode != 0
        assert "Terminé" not in resultat.stdout
        assert "vide" in resultat.stdout.lower()
        assert journal_stop.read_text() == "stop appelé\n"

    def test_json_invalide_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "invalid_json")

        assert resultat.returncode != 0
        assert "Terminé" not in resultat.stdout
        assert "JSON valide" in resultat.stdout
        assert journal_stop.read_text() == "stop appelé\n"
