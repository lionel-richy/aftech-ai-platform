"""Règle de choix du GPU Modal (backend/app/gpu_config.py) — aucune
dépendance à `modal`, donc testable même sans ce paquet installé.

L'intégration réelle (ce module chargé exactement comme `modal deploy` le
fait, depuis backend/ comme cwd) a été vérifiée manuellement avec
`modal.cli.import_refs.import_file_or_module` : import réussi avec
MODAL_GPU_TYPE non défini (-> L4) et rejet explicite avec MODAL_GPU_TYPE=A100.
"""

import pytest

from app.gpu_config import GPU_TYPE_DEFAUT, GPU_TYPES_AUTORISES, resoudre_gpu_type


def test_defaut_est_l4():
    assert GPU_TYPE_DEFAUT == "L4"
    assert resoudre_gpu_type(None) == "L4"


def test_t4_autorise_profil_economique():
    assert resoudre_gpu_type("T4") == "T4"


def test_l4_autorise():
    assert resoudre_gpu_type("L4") == "L4"


def test_a100_interdit():
    with pytest.raises(ValueError, match="A100"):
        resoudre_gpu_type("A100")


@pytest.mark.parametrize("valeur", ["H100", "G4", "a4000", "", "t4"])
def test_valeurs_inconnues_interdites(valeur):
    # "t4" (minuscule) : la casse n'est PAS tolérée silencieusement — mieux
    # vaut échouer clairement qu'accepter une faute de frappe qui
    # déploierait sur un GPU différent de celui voulu.
    with pytest.raises(ValueError):
        resoudre_gpu_type(valeur)


def test_espaces_autour_de_la_valeur_sont_tolere():
    # Les espaces de bord (ex. variable d'environnement mal copiée) sont
    # nettoyés avant comparaison — mais pas la casse (voir test ci-dessus).
    assert resoudre_gpu_type(" T4 ") == "T4"


def test_liste_autorisee_ne_contient_pas_a100():
    assert "A100" not in GPU_TYPES_AUTORISES
    assert set(GPU_TYPES_AUTORISES) == {"T4", "L4"}
