"""
Benchmark GPU reproductible (T4 / L4 / A100) pour AFTECH.

Compare le MÊME pipeline (Qwen3-4B-Instruct-2507 en 4 bits + BGE-M3 + FAISS,
mêmes questions, mêmes paramètres de génération, même seed) sur différents
GPU Colab. Réutilise directement backend/app/rag_engine.py — le moteur de
l'API — comme source unique de vérité : impossible qu'un paramètre diverge
entre les GPU testés, puisque c'est littéralement le même code qui tourne.

Sécurité (exigence explicite) : si le GPU réellement obtenu ne correspond
PAS au GPU demandé, le script s'arrête IMMÉDIATEMENT, avant d'écrire quoi
que ce soit — jamais un fichier "T4.json" obtenu sur un autre GPU.

Usage (sur Colab, via colab exec) :
    python scripts/gpu_benchmark.py --gpu-attendu T4 --output results/benchmarks/gpu/T4.json
"""

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Dossier Colab par défaut où run_gpu_benchmark.sh envoie backend/app/*.py
# (voir "envoyer uniquement les fichiers nécessaires" dans ce même script).
DOSSIER_BACKEND_COLAB_DEFAUT = "/content/backend"


def determiner_dossier_backend(fichier_script: str | None, racine_colab: str = DOSSIER_BACKEND_COLAB_DEFAUT) -> Path:
    """Détermine le dossier contenant le paquet "app" (backend/) à ajouter au sys.path.

    - Lancé normalement (`python scripts/gpu_benchmark.py`) : `__file__` est
      défini, on remonte au dossier racine du projet puis "backend".
    - Exécuté via `colab exec` : le code est passé à `exec()` dans un kernel
      Jupyter déjà démarré, où `__file__` n'existe PAS (NameError si on y
      accède directement) — on utilise alors /content/backend.

    Fonction pure (aucun accès à `__file__` ici) : testable sans dépendre du
    contexte d'exécution réel, voir tests/test_gpu_benchmark_helpers.py.
    """
    if fichier_script:
        return Path(fichier_script).resolve().parents[1] / "backend"
    return Path(racine_colab)


# Permet d'importer backend/app/rag_engine.py : le MÊME moteur que l'API.
# globals().get("__file__") plutôt que "__file__" directement : accéder à un
# nom absent lève NameError même dans une simple expression, alors que
# globals().get(...) renvoie None proprement (cas "colab exec").
sys.path.insert(0, str(determiner_dossier_backend(globals().get("__file__"))))

GPU_ATTENDUS_VALIDES = ("T4", "L4", "A100")

# Questions identiques pour tous les GPU (exigence explicite : ne jamais les
# faire varier selon le GPU testé).
QUESTIONS = [
    "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
    "Quel document contient les informations relatives à Azure ?",
    "Quel est l'objectif principal de l'EU AI Act ?",
    "Résume le sujet principal du document Accompagnement2004.pdf.",
    "Quel document parle de vLLM ?",
    "Quel est le nom du directeur financier d'AFTECH ?",
]

TOP_K = 8
REPETITIONS_DEFAUT = 3
SEED_DEFAUT = 42


def valider_gpu_attendu(gpu_attendu: str, gpu_obtenu: str) -> bool:
    """Compare le GPU réellement obtenu (ex. "Tesla T4", "NVIDIA A100-SXM4-40GB")
    au GPU demandé (ex. "T4", "A100").

    Fonction PURE (pas de dépendance GPU) : testée sans matériel dans
    backend/tests ou tests/ (voir scripts de test du benchmark).
    """
    if not gpu_obtenu:
        return False
    return gpu_attendu.strip().upper() in gpu_obtenu.strip().upper()


CONFIG_PATH_DEFAUT = "/content/benchmark_config.json"


def fusionner_config_fichier(args, parser):
    """"colab exec" ne transmet JAMAIS d'arguments personnalisés (déjà
    rencontré sur les autres scripts) : si --gpu-attendu/--output ne sont pas
    fournis en ligne de commande, on les lit depuis un petit fichier JSON
    téléversé par run_gpu_benchmark.sh (ex. /content/benchmark_config.json).

    Fonction PURE (ne touche à rien de global) : testable sans GPU, sans
    fichier réel (on lui passe un dict directement dans les tests).
    """
    if args.gpu_attendu and args.output:
        return args  # tout fourni en ligne de commande, rien à compléter

    if not os.path.isfile(args.config):
        parser.error(
            f"--gpu-attendu et --output sont requis (directement, ou via le fichier "
            f"de configuration {args.config}, absent ici)."
        )

    with open(args.config, encoding="utf-8") as f:
        config_fichier = json.load(f)

    args.gpu_attendu = args.gpu_attendu or config_fichier.get("gpu_attendu")
    args.output = args.output or config_fichier.get("output")
    args.index_dir = config_fichier.get("index_dir", args.index_dir)
    args.repetitions = config_fichier.get("repetitions", args.repetitions)
    args.seed = config_fichier.get("seed", args.seed)
    args.install_timing_file = config_fichier.get("install_timing_file", args.install_timing_file)

    if not args.gpu_attendu or not args.output:
        parser.error("Configuration incomplète : gpu_attendu et output sont requis.")

    return args


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark GPU reproductible AFTECH.")
    parser.add_argument("--gpu-attendu", choices=GPU_ATTENDUS_VALIDES, default=None)
    parser.add_argument("--output", default=None, help="Chemin du fichier JSON de sortie")
    parser.add_argument("--index-dir", default="data/indexes/aftech_documents")
    parser.add_argument("--repetitions", type=int, default=REPETITIONS_DEFAUT)
    parser.add_argument("--seed", type=int, default=SEED_DEFAUT)
    parser.add_argument(
        "--install-timing-file",
        default=None,
        help="Fichier JSON (écrit par run_gpu_benchmark.sh) contenant le temps d'installation des dépendances, si mesuré.",
    )
    parser.add_argument(
        "--config",
        default=CONFIG_PATH_DEFAUT,
        help="Fichier JSON de configuration, utilisé si --gpu-attendu/--output sont absents (cas colab exec).",
    )
    # parse_known_args (pas parse_args) : "colab exec" exécute ce code dans un
    # kernel Jupyter déjà lancé, dont les propres arguments (ex. "-f
    # <fichier-de-connexion>") sont visibles ici. On les ignore silencieusement
    # au lieu de planter dessus (même bug déjà rencontré sur les autres scripts).
    args, _ = parser.parse_known_args()
    return fusionner_config_fichier(args, parser)


def executer_commande(commande: list[str], timeout=10):
    try:
        resultat = subprocess.run(commande, capture_output=True, text=True, timeout=timeout)
        return resultat.stdout.strip() if resultat.returncode == 0 else None
    except Exception:
        return None


def obtenir_version_pilote_nvidia():
    sortie = executer_commande(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    return sortie.splitlines()[0].strip() if sortie else None


def obtenir_ram_systeme_go():
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for ligne in f:
                if ligne.startswith("MemTotal:"):
                    ko = int(ligne.split()[1])
                    return round(ko / (1024**2), 2)
    except Exception:
        pass
    return None


def obtenir_nom_cpu():
    try:
        with open("/proc/cpuinfo") as f:
            for ligne in f:
                if ligne.lower().startswith("model name"):
                    return ligne.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine() or None


class EchantillonneurGPU:
    """Échantillonne utilisation/puissance GPU via nvidia-smi en arrière-plan
    pendant une génération. Se désactive silencieusement si nvidia-smi est
    indisponible (ces métriques sont explicitement "si disponible" dans le
    cahier des charges)."""

    def __init__(self, intervalle_secondes: float = 0.5):
        self.intervalle_secondes = intervalle_secondes
        self._stop = threading.Event()
        self._thread = None
        self.utilisations: list[float] = []
        self.puissances_watts: list[float] = []
        self.disponible = executer_commande(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"]) is not None

    def _boucle(self):
        while not self._stop.is_set():
            sortie = executer_commande(
                ["nvidia-smi", "--query-gpu=utilization.gpu,power.draw", "--format=csv,noheader,nounits"], timeout=5
            )
            if sortie:
                try:
                    partie_util, partie_puissance = sortie.split(",")
                    self.utilisations.append(float(partie_util.strip()))
                    self.puissances_watts.append(float(partie_puissance.strip()))
                except ValueError:
                    pass
            self._stop.wait(self.intervalle_secondes)

    def __enter__(self):
        if self.disponible:
            self._thread = threading.Thread(target=self._boucle, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def resume(self) -> dict:
        return {
            "utilisation_gpu_moyenne_pourcent": round(statistics.mean(self.utilisations), 1) if self.utilisations else None,
            "puissance_moyenne_watts": round(statistics.mean(self.puissances_watts), 1) if self.puissances_watts else None,
            "puissance_max_watts": round(max(self.puissances_watts), 1) if self.puissances_watts else None,
        }


def mesurer_premier_token(engine, question: str) -> dict:
    """Mesure le temps avant le premier token généré (TTFT), via un appel de
    streaming DÉDIÉ et séparé (même modèle, même prompt, mêmes paramètres),
    pour ne jamais modifier le chemin de génération partagé avec l'API."""
    try:
        from transformers import TextIteratorStreamer
    except Exception as exc:
        return {"disponible": False, "raison": str(exc)}

    from app.rag_engine import MAX_NEW_TOKENS, SYSTEM_PROMPT

    passages = engine._rechercher_passages(question, TOP_K)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": engine._construire_prompt(question, passages)},
    ]
    inputs = engine.tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(engine.model.device)

    streamer = TextIteratorStreamer(engine.tokenizer, skip_special_tokens=True)
    kwargs = dict(inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, streamer=streamer)

    debut = time.perf_counter()
    thread = threading.Thread(target=engine.model.generate, kwargs=kwargs)
    thread.start()

    temps_premier_token = None
    for _ in streamer:
        if temps_premier_token is None:
            temps_premier_token = time.perf_counter() - debut
    thread.join()

    return {"disponible": True, "temps_premier_token_secondes": temps_premier_token}


def agreger(valeurs: list) -> dict | None:
    valeurs = [v for v in valeurs if v is not None]
    if not valeurs:
        return None
    return {
        "moyenne": statistics.mean(valeurs),
        "mediane": statistics.median(valeurs),
        "minimum": min(valeurs),
        "maximum": max(valeurs),
        "ecart_type": statistics.stdev(valeurs) if len(valeurs) > 1 else 0.0,
    }


def executer_un_appel(engine, torch_module, question: str) -> tuple[dict | None, list[dict]]:
    """Une seule exécution (recherche + génération + validation). Renvoie
    (mesure, erreurs) — mesure est None si une erreur CUDA/mémoire a eu lieu."""
    torch_module.cuda.reset_peak_memory_stats()
    memoire_avant = torch_module.cuda.memory_allocated()

    try:
        with EchantillonneurGPU() as echantillonneur:
            debut_total = time.perf_counter()
            resultat = engine.ask(question, top_k=TOP_K)
            temps_total_mesure = time.perf_counter() - debut_total
        stats_gpu = echantillonneur.resume()
    except torch_module.cuda.OutOfMemoryError as exc:
        return None, [{"type": "cuda_out_of_memory", "message": str(exc)}]
    except RuntimeError as exc:
        return None, [{"type": "cuda_runtime_error", "message": str(exc)}]

    memoire_pic = torch_module.cuda.max_memory_allocated()
    temps_generation = resultat["timings"]["generation_secondes"]

    mesure = {
        "status": resultat["status"],
        "answer": resultat["answer"],
        "tokens_entree": resultat["tokens_entree"],
        "tokens_generes": resultat["tokens_generes"],
        "tokens_par_seconde": (resultat["tokens_generes"] / temps_generation) if temps_generation > 0 else None,
        "temps_recherche_secondes": resultat["timings"]["recherche_secondes"],
        "temps_generation_secondes": temps_generation,
        "temps_total_secondes": temps_total_mesure,
        "memoire_gpu_avant_octets": memoire_avant,
        "memoire_gpu_pic_octets": memoire_pic,
        **stats_gpu,
    }
    return mesure, []


def main():
    args = parse_args()

    import torch

    torch.manual_seed(args.seed)

    print(f"GPU demandé : {args.gpu_attendu}")
    if not torch.cuda.is_available():
        print("ERREUR : aucun GPU CUDA détecté. Arrêt immédiat, rien n'est écrit.", file=sys.stderr)
        sys.exit(1)

    gpu_obtenu = torch.cuda.get_device_name(0)
    print(f"GPU obtenu  : {gpu_obtenu}")

    if not valider_gpu_attendu(args.gpu_attendu, gpu_obtenu):
        print(
            f"ERREUR : le GPU obtenu ('{gpu_obtenu}') ne correspond pas au GPU demandé "
            f"('{args.gpu_attendu}'). Arrêt immédiat, AUCUN fichier n'est écrit.",
            file=sys.stderr,
        )
        sys.exit(1)

    avertissements: list[str] = []
    if args.install_timing_file and os.path.isfile(args.install_timing_file):
        with open(args.install_timing_file, encoding="utf-8") as f:
            temps_installation = json.load(f).get("temps_installation_secondes")
    else:
        temps_installation = None
        avertissements.append(
            "Temps d'installation des dépendances non mesuré (fichier --install-timing-file absent)."
        )

    avertissements.append(
        "La génération déterministe (do_sample=False) limite mais ne garantit pas une "
        "reproductibilité bit-exacte entre GPU/versions de kernels CUDA différents."
    )

    vram_totale_octets = torch.cuda.get_device_properties(0).total_memory
    memoire_gpu_avant_chargement = torch.cuda.memory_allocated()

    from app import rag_engine
    from app.rag_engine import RagEngine

    engine = RagEngine(index_dir=args.index_dir)
    engine.load()

    if not engine.ready:
        print(f"ERREUR au chargement du moteur RAG : {engine.error}", file=sys.stderr)
        sys.exit(1)

    memoire_gpu_apres_chargement = torch.cuda.memory_allocated()

    import sentence_transformers
    import transformers
    import bitsandbytes

    configuration = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "gpu_demande": args.gpu_attendu,
        "gpu_obtenu": gpu_obtenu,
        "vram_totale_octets": vram_totale_octets,
        "version_cuda": torch.version.cuda,
        "version_pilote_nvidia": obtenir_version_pilote_nvidia(),
        "version_torch": torch.__version__,
        "version_transformers": transformers.__version__,
        "version_bitsandbytes": bitsandbytes.__version__,
        "version_sentence_transformers": sentence_transformers.__version__,
        "ram_systeme_go": obtenir_ram_systeme_go(),
        "cpu": obtenir_nom_cpu(),
        "taille_index_octets": os.path.getsize(os.path.join(args.index_dir, "index.faiss")),
        "nombre_documents": len(engine.manifest.get("pdf", [])),
        "nombre_passages": len(engine.chunks),
        "modele_embeddings": rag_engine.EMBEDDING_MODEL_NAME,
        "modele_llm": rag_engine.LLM_MODEL_NAME,
        "seed": args.seed,
        "repetitions": args.repetitions,
        "questions": QUESTIONS,
    }

    print("Mesure du temps avant le premier token (appel dédié)...")
    premier_token = mesurer_premier_token(engine, QUESTIONS[0])

    print("Échauffement (non comptabilisé)...")
    _, erreurs_echauffement = executer_un_appel(engine, torch, QUESTIONS[0])

    mesures_brutes = []
    erreurs: list[dict] = list(erreurs_echauffement)
    reponses_par_question: dict[str, list[dict]] = {}

    for question in QUESTIONS:
        reponses_par_question[question] = []
        for repetition in range(1, args.repetitions + 1):
            print(f"Question {QUESTIONS.index(question) + 1}/{len(QUESTIONS)}, répétition {repetition}/{args.repetitions}...")
            mesure, erreurs_appel = executer_un_appel(engine, torch, question)
            if mesure is None:
                erreurs.extend({**e, "question": question, "repetition": repetition} for e in erreurs_appel)
                continue
            mesure_complete = {"question": question, "repetition": repetition, **mesure}
            mesures_brutes.append(mesure_complete)
            reponses_par_question[question].append(mesure)

    # --- Agrégats globaux et par question ---
    def valeurs(cle, sous_ensemble=None):
        source = sous_ensemble if sous_ensemble is not None else mesures_brutes
        return [m[cle] for m in source]

    agregats = {
        "global": {
            "temps_recherche_secondes": agreger(valeurs("temps_recherche_secondes")),
            "temps_generation_secondes": agreger(valeurs("temps_generation_secondes")),
            "temps_total_secondes": agreger(valeurs("temps_total_secondes")),
            "tokens_par_seconde": agreger(valeurs("tokens_par_seconde")),
        },
        "par_question": {
            question: {
                "temps_total_secondes": agreger(valeurs("temps_total_secondes", mesures)),
                "tokens_par_seconde": agreger(valeurs("tokens_par_seconde", mesures)),
                "statuts": [m["status"] for m in mesures],
            }
            for question, mesures in reponses_par_question.items()
        },
    }

    reponses = [
        {
            "question": question,
            "reponses": [m["answer"] for m in mesures],
            "statuts": [m["status"] for m in mesures],
        }
        for question, mesures in reponses_par_question.items()
    ]

    resultat_final = {
        "configuration": configuration,
        "temps_installation_secondes": temps_installation,
        "temps_chargement": {
            "index_secondes": engine.timings_chargement.get("index_secondes"),
            "embedder_secondes": engine.timings_chargement.get("embedder_secondes"),
            "llm_secondes": engine.timings_chargement.get("llm_secondes"),
        },
        "premier_appel_a_froid": {
            "erreurs": erreurs_echauffement,
        },
        "premier_token": premier_token,
        "memoire_gpu_avant_chargement_octets": memoire_gpu_avant_chargement,
        "memoire_gpu_apres_chargement_octets": memoire_gpu_apres_chargement,
        "mesures_brutes": mesures_brutes,
        "agregats": agregats,
        "reponses": reponses,
        "erreurs": erreurs,
        "avertissements": avertissements,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultat_final, f, ensure_ascii=False, indent=2, default=str)

    print(f"Résultats enregistrés dans {args.output}")


if __name__ == "__main__":
    main()
