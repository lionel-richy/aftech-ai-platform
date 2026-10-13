"""Règle de choix du GPU Modal — isolée dans un module sans dépendance à
`modal`, pour rester testable même quand ce paquet n'est pas installé
(ex. sur ce Mac, où seul le mode dégradé sans GPU est testé localement).

Basé sur le benchmark réel (results/benchmarks/gpu/) pour Qwen3-4B-Instruct-2507
en 4 bits :
    T4   : 7.6 tokens/s,  22.48 s/réponse, pic 4.64 Go
    L4   : 12.4 tokens/s, 15.33 s/réponse, pic 3.02 Go
    A100 : 13.2 tokens/s, 15.06 s/réponse, pic 3.02 Go
L4 est quasiment aussi rapide que A100 pour ce modèle, mais nettement moins
coûteux : c'est le GPU recommandé pour la démonstration. T4 reste le profil
économique. A100 est explicitement interdit (aucun gain mesuré, coût plus
élevé).
"""

import os

GPU_TYPES_AUTORISES = ("T4", "L4")
GPU_TYPE_DEFAUT = "L4"


def resoudre_gpu_type(valeur_env: str | None = None) -> str:
    """Détermine le GPU à utiliser, en refusant toute valeur non autorisée.

    `valeur_env` permet de tester sans dépendre de la variable
    d'environnement réelle ; en usage normal, on laisse Modal lire
    MODAL_GPU_TYPE directement depuis l'environnement.
    """
    brut = valeur_env if valeur_env is not None else os.environ.get("MODAL_GPU_TYPE", GPU_TYPE_DEFAUT)
    valeur = brut.strip()
    if valeur not in GPU_TYPES_AUTORISES:
        raise ValueError(
            f"MODAL_GPU_TYPE={valeur!r} n'est pas autorisé. Valeurs acceptées : "
            f"{GPU_TYPES_AUTORISES}. A100 est explicitement interdit pour Qwen 4B "
            "(aucun gain mesuré, coût plus élevé — voir le benchmark GPU)."
        )
    return valeur
