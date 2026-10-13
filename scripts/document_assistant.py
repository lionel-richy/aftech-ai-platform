"""
Assistant documentaire AFTECH.

Ce script est un exemple simple de "RAG" (Retrieval-Augmented Generation) :
1) on retrouve les passages de documents les plus proches d'une question
   (grâce à des embeddings + une similarité cosinus) ;
2) on donne ces passages à un modèle de langage (Qwen3) pour qu'il rédige
   une réponse UNIQUEMENT à partir de ce contenu.

L'idée : au lieu de laisser le modèle "inventer" une réponse, on l'oblige
à s'appuyer sur les vrais documents de l'entreprise.
"""

import glob
import json
import os
import time

import torch
from sentence_transformers import SentenceTransformer, util
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DATA_DIR = "data/samples"
RESULTS_PATH = "results/benchmarks/rag_test.json"

# Modèle d'embeddings : transforme un texte en une liste de nombres (un vecteur)
# qui représente son sens. Deux textes proches en sens auront des vecteurs proches.
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

# Modèle de génération : celui qui rédige la réponse finale
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

TOP_K = 3  # nombre de passages les plus pertinents à récupérer

# Score de similarité minimum pour accepter d'interroger Qwen.
# En dessous de ce seuil, on considère que les documents ne parlent
# pas du sujet de la question, donc ça ne sert à rien de demander à Qwen.
MIN_SCORE = 0.60

# Questions posées automatiquement à la fin du script.
# La dernière teste volontairement un sujet absent des documents,
# pour vérifier que l'assistant sait dire "je ne sais pas".
QUESTIONS = [
    "Quelle est la longueur minimale d'un mot de passe ?",
    "Dans combien de temps un incident P1 doit-il être pris en charge ?",
    "Combien de jours avant le départ faut-il demander un congé ?",
    "Quel est le chiffre d'affaires annuel d'AFTECH ?",
]

# Message système renforcé : on interdit explicitement à Qwen de compléter
# avec ses propres connaissances générales, pour éviter qu'il "invente".
SYSTEM_PROMPT = (
    "Tu es un assistant documentaire. Tu réponds toujours en français, de façon "
    "simple et claire. Tu dois répondre UNIQUEMENT à partir du contexte fourni "
    "dans le message de l'utilisateur. Ne complète jamais avec tes connaissances "
    "générales, même si tu penses connaître la réponse. Si le contexte ne "
    "contient pas clairement la réponse, réponds exactement : "
    '"Information non trouvée dans les documents".'
)

REPONSE_NON_TROUVEE = "Information non trouvée dans les documents."


def charger_paragraphes():
    """Lit tous les fichiers .txt de data/samples et les découpe en paragraphes.

    On découpe par paragraphe (et non par document entier) pour que la
    recherche de similarité retrouve des passages précis, pas des textes
    entiers trop longs.
    """
    paragraphes = []  # le texte de chaque paragraphe
    sources = []  # le nom du fichier d'où vient chaque paragraphe (même index)

    for chemin in sorted(glob.glob(os.path.join(DATA_DIR, "*.txt"))):
        with open(chemin, encoding="utf-8") as fichier:
            contenu = fichier.read()

        # Un paragraphe = un bloc de texte séparé par une ligne vide
        blocs = [bloc.strip() for bloc in contenu.split("\n\n") if bloc.strip()]

        for bloc in blocs:
            paragraphes.append(bloc)
            sources.append(os.path.basename(chemin))

    return paragraphes, sources


def recuperer_passages(question, embedder, embeddings_paragraphes, paragraphes, sources):
    """Retrouve les TOP_K paragraphes les plus proches de la question.

    On compare le vecteur de la question à celui de chaque paragraphe avec
    la similarité cosinus : plus le score est proche de 1, plus les deux
    textes parlent de la même chose.
    """
    embedding_question = embedder.encode(question, convert_to_tensor=True)
    scores = util.cos_sim(embedding_question, embeddings_paragraphes)[0]

    nb_resultats = min(TOP_K, len(paragraphes))
    meilleurs_indices = torch.topk(scores, k=nb_resultats).indices.tolist()

    resultats = []
    for indice in meilleurs_indices:
        resultats.append(
            {
                "texte": paragraphes[indice],
                "source": sources[indice],
                "score": float(scores[indice]),
            }
        )
    return resultats


def construire_prompt(question, passages):
    """Construit le texte envoyé à Qwen (le contexte, plus loin les consignes
    strictes sont déjà posées dans SYSTEM_PROMPT)."""
    contexte = "\n\n".join(f"[{p['source']}] {p['texte']}" for p in passages)
    return f"Contexte :\n{contexte}\n\nQuestion : {question}"


def main():
    # --- Étape 1 : préparer les documents (la partie "Retrieval" du RAG) ---
    print("Lecture et découpage des documents...")
    paragraphes, sources = charger_paragraphes()
    print(f"{len(paragraphes)} paragraphes trouvés dans {len(set(sources))} fichiers.\n")

    # bge-m3 tourne très bien sur CPU : pas besoin du GPU pour cette étape,
    # on garde le GPU libre pour le modèle de génération (Qwen)
    print(f"Chargement du modèle d'embeddings {EMBEDDING_MODEL_NAME} sur CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Calcul des embeddings de tous les paragraphes...\n")
    embeddings_paragraphes = embedder.encode(paragraphes, convert_to_tensor=True)

    # --- Étape 2 : préparer le modèle de génération (la partie "Generation" du RAG) ---
    if not torch.cuda.is_available():
        raise RuntimeError("Aucun GPU détecté. Ce script doit tourner sur une session Colab avec GPU.")

    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU détecté : {gpu_name}")

    # La Tesla T4 ne gère pas correctement bfloat16 : on force float16 dans ce cas précis
    if "T4" in gpu_name:
        compute_dtype = torch.float16
    elif torch.cuda.is_bf16_supported():
        compute_dtype = torch.bfloat16
    else:
        compute_dtype = torch.float16
    print(f"Type de calcul utilisé : {compute_dtype}")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Chargement du modèle {LLM_MODEL_NAME} en 4 bits...\n")
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL_NAME,
        quantization_config=quant_config,
        device_map="auto",
    )

    # --- Étape 3 : répondre à chaque question ---
    resultats_tests = []  # on y accumule un résumé de chaque test, pour le JSON final

    for question in QUESTIONS:
        print("=" * 70)
        print(f"Question : {question}\n")

        passages = recuperer_passages(question, embedder, embeddings_paragraphes, paragraphes, sources)
        meilleur_score = passages[0]["score"] if passages else 0.0

        print("Passages retrouvés (fichier source + score de similarité) :")
        for p in passages:
            apercu = p["texte"][:80].replace("\n", " ")
            print(f"  - [{p['source']}] score={p['score']:.3f} : {apercu}...")
        print(f"Meilleur score : {meilleur_score:.3f}")

        # Si même le meilleur passage est trop peu pertinent, inutile d'interroger
        # Qwen : les documents ne parlent probablement pas de ce sujet.
        if meilleur_score < MIN_SCORE:
            reponse = REPONSE_NON_TROUVEE
            sources_utilisees = []
            temps_reponse = 0.0
            print(f"\nScore sous le seuil ({MIN_SCORE}), Qwen n'est pas interrogé.")
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": construire_prompt(question, passages)},
            ]

            # return_dict=True : on récupère input_ids ET attention_mask, ce qu'attend generate()
            inputs = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            ).to(model.device)

            debut = time.perf_counter()
            output_ids = model.generate(
                **inputs,
                max_new_tokens=250,
                do_sample=False,
            )
            temps_reponse = time.perf_counter() - debut

            # On ne garde que les tokens générés, pas la question renvoyée dans la sortie
            generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
            reponse = tokenizer.decode(generated_ids, skip_special_tokens=True)

            # Sources réellement utilisées = celles des passages envoyés à Qwen
            sources_utilisees = [p["source"] for p in passages]

        print(f"\nRéponse : {reponse}")
        print(f"Sources utilisées : {sources_utilisees}")
        print(f"Temps de réponse : {temps_reponse:.2f} s\n")

        resultats_tests.append(
            {
                "question": question,
                "reponse": reponse,
                "sources": sources_utilisees,
                "scores": [p["score"] for p in passages],
                "temps_reponse_secondes": temps_reponse,
            }
        )

    # --- Étape 4 : sauvegarde des résultats pour pouvoir comparer les tests entre eux ---
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(resultats_tests, f, ensure_ascii=False, indent=2)
    print(f"Résultats enregistrés dans {RESULTS_PATH}")


if __name__ == "__main__":
    main()
