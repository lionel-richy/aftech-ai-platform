"""
Construit results/benchmarks/gpu/comparison.csv et recommendation.md à partir
des fichiers T4.json / L4.json / A100.json produits par gpu_benchmark.py.

Tourne ENTIÈREMENT en local (pas de GPU requis) : lit des fichiers JSON déjà
téléchargés depuis Colab, ne relance jamais de calcul lourd.

Important : si un GPU n'a pas été benchmické, il est absent du CSV plutôt que
représenté avec des valeurs inventées — et recommendation.md le dit
explicitement ("Benchmark non exécuté").
"""

import argparse
import csv
import json
import os
from pathlib import Path

GPU_CONNUS = ("T4", "L4", "A100")

# Guidance générale (PAS mesurée par ce benchmark, clairement signalée comme
# telle) pour les catégories hors du périmètre testé ici.
RECOMMANDATIONS_NON_MESUREES = {
    "Qwen plus grand (ex. 14B/32B)": (
        "Non mesuré dans ce benchmark (qui teste uniquement Qwen 4B). Un modèle "
        "14B-32B en 4 bits demande typiquement 16-24 Go de VRAM : à tester sur "
        "L4 (24 Go) ou A100 (40/80 Go), pas sur T4 (16 Go, souvent trop juste)."
    ),
    "Whisper (transcription audio)": (
        "Non mesuré dans ce benchmark. Whisper (même en large-v3) tient "
        "largement sur un T4 : généralement le choix le moins coûteux pour "
        "cet usage, sauf besoin de très haut débit de transcription simultanée."
    ),
    "OCR": (
        "Non mesuré dans ce benchmark. La plupart des moteurs OCR modernes "
        "(ex. basés transformers légers) tournent confortablement sur un T4."
    ),
    "Vision (classification/détection d'images)": (
        "Non mesuré dans ce benchmark. Dépend fortement du modèle choisi ; un "
        "T4 ou L4 suffit pour la plupart des modèles de vision classiques."
    ),
    "Génération d'images": (
        "Non mesuré dans ce benchmark. Les modèles de diffusion modernes "
        "profitent nettement d'un L4 ou A100 (VRAM et débit mémoire plus "
        "élevés) ; un T4 reste utilisable mais plus lent."
    ),
}


def charger_resultats(dossier: Path) -> dict:
    resultats = {}
    for gpu in GPU_CONNUS:
        chemin = dossier / f"{gpu}.json"
        if chemin.is_file():
            with open(chemin, encoding="utf-8") as f:
                resultats[gpu] = json.load(f)
    return resultats


def extraire_ligne_csv(gpu: str, donnees: dict) -> dict:
    config = donnees.get("configuration", {})
    agregats_global = donnees.get("agregats", {}).get("global", {})

    def valeur_agregat(cle, sous_cle="moyenne"):
        agregat = agregats_global.get(cle)
        return agregat.get(sous_cle) if agregat else None

    mesures = donnees.get("mesures_brutes", [])
    pics_memoire = [m["memoire_gpu_pic_octets"] for m in mesures if m.get("memoire_gpu_pic_octets") is not None]

    return {
        "gpu": gpu,
        "gpu_obtenu": config.get("gpu_obtenu"),
        "vram_totale_go": round(config.get("vram_totale_octets", 0) / (1024**3), 2) if config.get("vram_totale_octets") else None,
        "nb_documents": config.get("nombre_documents"),
        "nb_passages": config.get("nombre_passages"),
        "temps_chargement_index_s": donnees.get("temps_chargement", {}).get("index_secondes"),
        "temps_chargement_bge_s": donnees.get("temps_chargement", {}).get("embedder_secondes"),
        "temps_chargement_qwen_s": donnees.get("temps_chargement", {}).get("llm_secondes"),
        "temps_premier_token_s": (donnees.get("premier_token") or {}).get("temps_premier_token_secondes"),
        "temps_recherche_moyen_s": valeur_agregat("temps_recherche_secondes"),
        "temps_generation_moyen_s": valeur_agregat("temps_generation_secondes"),
        "temps_total_moyen_s": valeur_agregat("temps_total_secondes"),
        "tokens_par_seconde_moyen": valeur_agregat("tokens_par_seconde"),
        "memoire_gpu_pic_go_max": round(max(pics_memoire) / (1024**3), 2) if pics_memoire else None,
        "nb_erreurs": len(donnees.get("erreurs", [])),
        "nb_reponses_complete": sum(1 for m in mesures if m.get("status") == "COMPLETE"),
        "nb_reponses_partial": sum(1 for m in mesures if m.get("status") == "PARTIAL"),
        "nb_reponses_not_found": sum(1 for m in mesures if m.get("status") == "NOT_FOUND"),
    }


def construire_csv(resultats: dict, chemin_sortie: Path) -> list[dict]:
    lignes = [extraire_ligne_csv(gpu, donnees) for gpu, donnees in resultats.items()]
    os.makedirs(chemin_sortie.parent, exist_ok=True)

    if not lignes:
        # Aucun résultat : on écrit un CSV avec seulement l'en-tête, pas de
        # ligne inventée.
        colonnes = [
            "gpu", "gpu_obtenu", "vram_totale_go", "nb_documents", "nb_passages",
            "temps_chargement_index_s", "temps_chargement_bge_s", "temps_chargement_qwen_s",
            "temps_premier_token_s", "temps_recherche_moyen_s", "temps_generation_moyen_s",
            "temps_total_moyen_s", "tokens_par_seconde_moyen", "memoire_gpu_pic_go_max",
            "nb_erreurs", "nb_reponses_complete", "nb_reponses_partial", "nb_reponses_not_found",
        ]
        with open(chemin_sortie, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=colonnes).writeheader()
        return []

    colonnes = list(lignes[0].keys())
    with open(chemin_sortie, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(lignes)

    return lignes


def charger_usage_colab(dossier: Path, gpu: str) -> tuple[str | None, str | None]:
    avant = dossier / f"{gpu}_usage_avant.txt"
    apres = dossier / f"{gpu}_usage_apres.txt"
    texte_avant = avant.read_text(encoding="utf-8") if avant.is_file() else None
    texte_apres = apres.read_text(encoding="utf-8") if apres.is_file() else None
    return texte_avant, texte_apres


def construire_recommendation_md(resultats: dict, lignes_csv: list[dict], dossier: Path) -> str:
    lignes_md = ["# Recommandation GPU — AFTECH AI Platform", ""]

    gpu_testes = list(resultats.keys())
    gpu_manquants = [g for g in GPU_CONNUS if g not in gpu_testes]

    if not gpu_testes:
        lignes_md.append("**Benchmark non exécuté.** Aucun fichier T4.json / L4.json / A100.json trouvé.")
        lignes_md.append("")
        lignes_md.append("Lancez `./scripts/run_gpu_benchmark.sh <T4|L4|A100>` puis relancez ce script.")
        return "\n".join(lignes_md)

    if gpu_manquants:
        lignes_md.append(f"⚠️ GPU non testés (absents de la comparaison) : {', '.join(gpu_manquants)}.")
        lignes_md.append("")

    lignes_md.append("## Mesuré dans ce benchmark")
    lignes_md.append("")

    ligne_par_gpu = {l["gpu"]: l for l in lignes_csv}

    lignes_md.append("### Qwen/Qwen3-4B-Instruct-2507 (4 bits)")
    for gpu in gpu_testes:
        l = ligne_par_gpu[gpu]
        lignes_md.append(
            f"- **{gpu}** ({l['gpu_obtenu']}) : {l['tokens_par_seconde_moyen']:.1f} tokens/s en moyenne, "
            f"{l['temps_total_moyen_s']:.2f} s/réponse en moyenne, pic mémoire {l['memoire_gpu_pic_go_max']} Go "
            f"(sur {l['vram_totale_go']} Go disponibles), {l['nb_erreurs']} erreur(s)."
            if l["tokens_par_seconde_moyen"] is not None
            else f"- **{gpu}** : données incomplètes (voir {gpu}.json)."
        )
    if gpu_testes:
        plus_rapide = max(
            (l for l in lignes_csv if l["tokens_par_seconde_moyen"] is not None),
            key=lambda l: l["tokens_par_seconde_moyen"],
            default=None,
        )
        if plus_rapide:
            lignes_md.append("")
            lignes_md.append(
                f"→ Recommandation **Qwen 4B** : {plus_rapide['gpu']} est le plus rapide mesuré "
                f"({plus_rapide['tokens_par_seconde_moyen']:.1f} tokens/s). Si le budget est serré et que "
                "la latence mesurée sur T4 reste acceptable pour l'usage visé, T4 reste le choix le moins coûteux."
            )
    lignes_md.append("")

    lignes_md.append("### Embeddings (BAAI/bge-m3)")
    lignes_md.append(
        "- Calculé sur CPU dans ce pipeline (voir `temps_chargement_bge_s` dans comparison.csv) : "
        "aucun GPU n'est nécessaire pour les embeddings tels qu'utilisés ici."
    )
    lignes_md.append("")

    lignes_md.append("### Développement quotidien")
    lignes_md.append(
        "- Le GPU le moins coûteux testé qui reste fonctionnel (0 erreur CUDA/mémoire) est recommandé "
        "pour itérer pendant le développement — voir la colonne `nb_erreurs` de comparison.csv."
    )
    lignes_md.append("")

    lignes_md.append("### Démonstration multi-utilisateur")
    lignes_md.append(
        "- Ce benchmark exécute les requêtes en séquence (pas de charge concurrente simulée) : "
        "aucune recommandation de capacité multi-utilisateur ne peut être tirée de ces chiffres seuls. "
        "Un test de charge concurrente dédié serait nécessaire avant toute recommandation ici."
    )
    lignes_md.append("")

    lignes_md.append("## Non mesuré dans ce benchmark (guidance générale)")
    lignes_md.append("")
    for categorie, texte in RECOMMANDATIONS_NON_MESUREES.items():
        lignes_md.append(f"### {categorie}")
        lignes_md.append(f"- {texte}")
        lignes_md.append("")

    lignes_md.append("## Consommation Colab (CCU)")
    lignes_md.append("")
    au_moins_une_mesure = False
    for gpu in gpu_testes:
        avant, apres = charger_usage_colab(dossier, gpu)
        if avant or apres:
            au_moins_une_mesure = True
            lignes_md.append(f"### {gpu}")
            lignes_md.append("```")
            lignes_md.append(f"Avant : {avant.strip() if avant else 'non capturé'}")
            lignes_md.append(f"Après : {apres.strip() if apres else 'non capturé'}")
            lignes_md.append("```")
            lignes_md.append("")
    if not au_moins_une_mesure:
        lignes_md.append(
            "Non mesuré automatiquement (fichiers `<GPU>_usage_avant.txt` / `<GPU>_usage_apres.txt` absents). "
            "Si `colab usage` n'était pas disponible localement pendant le run, copiez son résultat "
            "manuellement avant/après le prochain benchmark — **on ne invente pas** de CCU consommées ici."
        )

    return "\n".join(lignes_md)


def main():
    parser = argparse.ArgumentParser(description="Construit comparison.csv et recommendation.md depuis les JSON de benchmark GPU.")
    parser.add_argument("--dossier", default="results/benchmarks/gpu", help="Dossier contenant T4.json/L4.json/A100.json")
    args = parser.parse_args()

    dossier = Path(args.dossier)
    resultats = charger_resultats(dossier)

    lignes_csv = construire_csv(resultats, dossier / "comparison.csv")
    print(f"comparison.csv écrit ({len(lignes_csv)} ligne(s)) dans {dossier / 'comparison.csv'}")

    contenu_md = construire_recommendation_md(resultats, lignes_csv, dossier)
    chemin_md = dossier / "recommendation.md"
    os.makedirs(chemin_md.parent, exist_ok=True)
    chemin_md.write_text(contenu_md, encoding="utf-8")
    print(f"recommendation.md écrit dans {chemin_md}")


if __name__ == "__main__":
    main()
