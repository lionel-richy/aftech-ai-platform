"""
Assistant documentaire AFTECH — version multi-PDF, avec index réutilisable.

Ce script NE recalcule JAMAIS les embeddings des documents : il charge
l'index FAISS déjà construit par scripts/build_document_index.py, et calcule
uniquement l'embedding de la question posée. C'est ce qui rend la recherche
quasi instantanée même avec plusieurs PDF volumineux.

Le mécanisme de sécurité est repris tel quel de scripts/pdf_assistant.py :
- la réponse de Qwen est découpée en affirmations, chacune avec sa preuve
  (passage + citation) ;
- chaque affirmation doit passer deux vérifications indépendantes (la
  citation existe-t-elle dans le passage, ET un second appel à Qwen sans
  accès au document confirme-t-il qu'elle prouve l'affirmation) ;
- une affirmation qui échoue à l'un des deux tests est supprimée.
Seule différence : le fichier source de chaque affirmation est retrouvé à
partir de NOS métadonnées de recherche (pas du texte généré par Qwen), pour
ne jamais faire confiance à Qwen sur le nom du fichier qu'il cite.
"""

import argparse
import json
import os
import re
import time
import unicodedata

import faiss
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DOSSIER_INDEX_DEFAUT = "data/indexes/aftech_documents"
RESULTS_PATH = "results/benchmarks/multi_document_test.json"

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

TOP_K = 8  # nombre de passages recherchés, tous documents confondus
MAX_NEW_TOKENS = 400
CITATION_MAX_CARACTERES = 200

REPONSE_NON_TROUVEE = "Information non trouvée dans les documents."
SEUIL_STATUT_COMPLETE = 3  # nombre d'affirmations validées à partir duquel le statut est COMPLETE

# Questions de test posées automatiquement à la fin du script.
QUESTIONS = [
    "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
    "Qu'est-ce que Microsoft Azure ?",
    "Résume le sujet principal du document Accompagnement2004.pdf.",
    "Quel document parle de vLLM ?",
    "Quel document contient des informations relatives à Azure ?",
    "Quel est le nom du directeur financier d'AFTECH ?",
]

# Message système : les passages peuvent venir de PDF différents, identifiés
# P1, P2, ... Qwen doit toujours découper sa réponse en affirmations, chacune
# justifiée par un passage + une page + une citation exacte.
SYSTEM_PROMPT = (
    "Tu es un assistant documentaire. Tu réponds toujours en français. Les "
    "passages fournis peuvent provenir de documents différents et sont "
    "identifiés par P1, P2, P3, etc. Tu dois répondre UNIQUEMENT à partir de "
    "ces passages. Ne complète jamais avec tes connaissances générales, même "
    "si tu penses connaître la réponse.\n\n"
    "Si les passages ne contiennent pas clairement la réponse, réponds "
    f'uniquement avec la phrase exacte : "{REPONSE_NON_TROUVEE}" (rien d\'autre).\n\n'
    "Sinon, découpe ta réponse en affirmations séparées : une seule affirmation "
    "pour une réponse simple, ou une affirmation distincte par élément si la "
    "réponse est une liste ou une synthèse à plusieurs points (6 éléments "
    "maximum). Pour CHAQUE affirmation, utilise STRICTEMENT ce format, sur 4 "
    "lignes :\n"
    "AFFIRMATION: <une seule affirmation, phrase complète>\n"
    "PASSAGE: <identifiant, ex. P2>\n"
    "PAGE: <numéro de page>\n"
    f'CITATION: "<citation copiée EXACTEMENT depuis ce passage, {CITATION_MAX_CARACTERES} '
    'caractères maximum>"\n\n'
    "Répète ce bloc de 4 lignes pour chaque affirmation. Termine toujours tes phrases.\n\n"
    "Cas particulier important : si la question demande QUEL document, fichier "
    "ou passage traite d'un sujet (par exemple \"quel document parle de X ?\"), "
    "ne réponds PAS \"non trouvée\" simplement parce qu'aucune phrase ne dit "
    "littéralement \"ce document parle de X\" — il suffit qu'un passage "
    "contienne clairement des informations sur ce sujet pour que tu puisses "
    "répondre. Dans ce cas, formule l'AFFIRMATION comme une information "
    "concrète tirée de ce passage (pas besoin de deviner ou de répéter le nom "
    "du fichier : il sera ajouté automatiquement à partir du passage cité)."
)

# Le vérificateur ne voit JAMAIS le document : seulement la question,
# l'affirmation et la citation censée la prouver.
VERIFICATEUR_SYSTEM_PROMPT = (
    "Tu es un vérificateur strict. Tu reçois une question, une affirmation et une "
    "citation censée prouver cette affirmation. Réponds par un seul mot : "
    "SUPPORTED si la citation prouve clairement l'affirmation pour cette question, "
    "ou NOT_SUPPORTED si ce n'est pas le cas ou si c'est ambigu. N'écris rien d'autre."
)


def parse_args():
    parser = argparse.ArgumentParser(description="Interroge l'index documentaire multi-PDF AFTECH.")
    parser.add_argument(
        "--index-dir",
        default=DOSSIER_INDEX_DEFAUT,
        help=f"Dossier contenant index.faiss, chunks.json, manifest.json (défaut : {DOSSIER_INDEX_DEFAUT})",
    )
    # parse_known_args (et non parse_args) : "colab exec" exécute ce code dans
    # un kernel Jupyter déjà lancé, dont les propres arguments (ex. "-f
    # <fichier-de-connexion>") sont visibles ici. On les ignore silencieusement
    # au lieu de planter dessus.
    args, _ = parser.parse_known_args()
    return args


def charger_index(index_dir):
    index = faiss.read_index(os.path.join(index_dir, "index.faiss"))
    with open(os.path.join(index_dir, "chunks.json"), encoding="utf-8") as f:
        chunks = json.load(f)
    with open(os.path.join(index_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return index, chunks, manifest


def rechercher_passages(question, embedder, index, chunks, top_k=TOP_K):
    """Calcule UNIQUEMENT l'embedding de la question (les documents sont déjà
    indexés) et cherche les passages les plus proches, tous PDF confondus."""
    embedding_question = embedder.encode(
        [question], convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")

    nb = min(top_k, len(chunks))
    scores, indices = index.search(embedding_question, nb)

    resultats = []
    for rang, (score, indice) in enumerate(zip(scores[0], indices[0])):
        if indice < 0:
            continue
        chunk = chunks[indice]
        resultats.append(
            {
                "id": f"P{rang + 1}",
                "texte": chunk["texte"],
                "source": chunk["source"],
                "page": chunk["page"],
                "score": float(score),
            }
        )
    return resultats


def construire_prompt(question, passages):
    contexte = "\n\n".join(
        f"[{p['id']} | fichier {p['source']} | page {p['page']}] {p['texte']}" for p in passages
    )
    return f"Passages :\n{contexte}\n\nQuestion : {question}"


# Caractères Unicode invisibles à supprimer (trait d'union invisible, espaces
# et joints de largeur nulle) : la mise en page d'un PDF en ajoute souvent
# sans qu'on les voie.
CARACTERES_INVISIBLES = "­​‌‍⁠﻿"


def normalize_text(texte):
    """Normalise un texte pour comparer citation et passage de façon fiable
    (identique à scripts/pdf_assistant.py) : NFKC, espaces insécables,
    caractères invisibles, séquences "\\n" littérales et vrais retours à la
    ligne, espaces multiples, minuscules pour la comparaison."""
    texte = unicodedata.normalize("NFKC", texte)
    texte = texte.replace(" ", " ").replace(" ", " ")

    for caractere in CARACTERES_INVISIBLES:
        texte = texte.replace(caractere, "")

    texte = texte.replace("\\n", " ")
    texte = texte.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texte = " ".join(texte.split())

    return texte.lower()


PATTERN_AFFIRMATION = re.compile(
    r"AFFIRMATION\s*:\s*(?P<affirmation>.+?)\s*"
    r"PASSAGE\s*:\s*(?P<passage_id>\S+)\s*"
    r"PAGE\s*:\s*(?P<page>\d+)\s*"
    r'CITATION\s*:\s*"(?P<citation>.+?)"',
    re.IGNORECASE | re.DOTALL,
)


def parser_affirmations(texte_brut):
    """Extrait la liste des affirmations (avec leur preuve) du format structuré.
    Une liste vide signifie que Qwen a répondu directement (typiquement la
    phrase "non trouvée")."""
    return [
        {
            "affirmation": m.group("affirmation").strip(),
            "passage_id": m.group("passage_id").strip().upper(),
            "page": int(m.group("page")),
            "citation": m.group("citation").strip(),
        }
        for m in PATTERN_AFFIRMATION.finditer(texte_brut)
    ]


def citation_est_presente(citation, passage):
    """Vérification n°1 : la citation existe-t-elle mot pour mot dans le
    passage COMPLET désigné (pas un extrait tronqué) ?"""
    if not passage or not citation.strip():
        return False
    return normalize_text(citation) in normalize_text(passage["texte"])


def generer_texte(messages, tokenizer, model, max_new_tokens):
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)

    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
    )

    generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True)


def verifier_affirmation(question, affirmation, citation, tokenizer, model):
    """Vérification n°2 : un second appel à Qwen, SANS le document, qui ne
    voit que la question, l'affirmation et la citation."""
    messages = [
        {"role": "system", "content": VERIFICATEUR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question : {question}\n"
                f"Affirmation : {affirmation}\n"
                f'Citation : "{citation}"'
            ),
        },
    ]
    verdict_brut = generer_texte(messages, tokenizer, model, max_new_tokens=10).strip().upper()

    if "NOT_SUPPORTED" in verdict_brut:
        return False
    return "SUPPORTED" in verdict_brut


def formater_affirmation_avec_source(a):
    return f"{a['affirmation']} [source : {a['fichier']}, page {a['page']}]"


def charger_modele_qwen():
    if not torch.cuda.is_available():
        raise RuntimeError("Aucun GPU détecté. Ce script doit tourner sur une session Colab avec GPU.")

    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU détecté : {gpu_name}")

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
    return tokenizer, model


def main():
    args = parse_args()

    print(f"Chargement de l'index depuis {args.index_dir}...")
    debut_indexation = time.perf_counter()
    index, chunks, manifest = charger_index(args.index_dir)
    temps_indexation = time.perf_counter() - debut_indexation
    print(
        f"Index chargé en {temps_indexation:.2f} s : {len(chunks)} passages, "
        f"{len(manifest.get('pdf', []))} PDF ({', '.join(manifest.get('pdf', []))})."
    )

    print(f"\nChargement du modèle d'embeddings {EMBEDDING_MODEL_NAME} (question uniquement)...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    tokenizer, model = charger_modele_qwen()

    resultats_tests = []

    for question in QUESTIONS:
        print("=" * 70)
        print(f"Question : {question}\n")

        debut_recherche = time.perf_counter()
        passages_trouves = rechercher_passages(question, embedder, index, chunks)
        temps_recherche = time.perf_counter() - debut_recherche

        passages_par_id = {p["id"]: p for p in passages_trouves}

        print("Passages retrouvés (fichier, page, score, court extrait) :")
        for p in passages_trouves:
            extrait = p["texte"][:120].replace("\n", " ")
            print(f"  - {p['id']} | {p['source']} | page {p['page']} | score={p['score']:.3f} : {extrait}...")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": construire_prompt(question, passages_trouves)},
        ]

        debut_generation = time.perf_counter()
        reponse_brute = generer_texte(messages, tokenizer, model, MAX_NEW_TOKENS)

        affirmations = parser_affirmations(reponse_brute)

        for aff in affirmations:
            passage = passages_par_id.get(aff["passage_id"])
            aff["citation_presente"] = citation_est_presente(aff["citation"], passage)

            if aff["citation_presente"]:
                aff["preuve_supported"] = verifier_affirmation(
                    question, aff["affirmation"], aff["citation"], tokenizer, model
                )
            else:
                aff["preuve_supported"] = False

            aff["affirmation_validee"] = aff["citation_presente"] and aff["preuve_supported"]

            # Fichier et page CITÉS À PARTIR DE NOS MÉTADONNÉES DE RECHERCHE,
            # jamais du texte généré par Qwen : on ne lui fait pas confiance
            # sur le nom exact du fichier ou le numéro de page.
            if passage:
                aff["fichier"] = passage["source"]
                aff["page"] = passage["page"]
            else:
                aff["fichier"] = None

        temps_generation = time.perf_counter() - debut_generation

        affirmations_gardees = [a for a in affirmations if a["affirmation_validee"]]

        if not affirmations_gardees:
            reponse_finale = REPONSE_NON_TROUVEE
        elif len(affirmations_gardees) == 1:
            reponse_finale = formater_affirmation_avec_source(affirmations_gardees[0])
        else:
            reponse_finale = "\n".join(
                f"- {formater_affirmation_avec_source(a)}" for a in affirmations_gardees
            )

        nb_validees = len(affirmations_gardees)
        if nb_validees == 0:
            statut = "NOT_FOUND"
        elif nb_validees < SEUIL_STATUT_COMPLETE:
            statut = "PARTIAL"
        else:
            statut = "COMPLETE"

        print(f"\nRéponse :\n{reponse_finale}")
        print(f"Statut : {statut}")
        if statut == "PARTIAL":
            print("Réponse partielle : certains éléments peuvent manquer.")
        print("Affirmations :")
        if affirmations:
            for a in affirmations:
                statut_affirmation = "validée" if a["affirmation_validee"] else "SUPPRIMÉE"
                print(
                    f"  - [{statut_affirmation}] {a['affirmation']!r} "
                    f"({a.get('fichier')}, page {a['page']}) "
                    f"citation_presente={a['citation_presente']} "
                    f"preuve_supported={a['preuve_supported']}"
                )
        else:
            print("  (aucune)")
        print(
            f"Temps : indexation={temps_indexation:.2f}s "
            f"recherche={temps_recherche:.2f}s "
            f"génération={temps_generation:.2f}s\n"
        )

        fichiers_pages_utilises = sorted(
            {(a["fichier"], a["page"]) for a in affirmations_gardees if a["fichier"]}
        )

        resultats_tests.append(
            {
                "question": question,
                "reponse": reponse_finale,
                "statut": statut,
                "fichiers_pages_utilises": [
                    {"fichier": f, "page": p} for f, p in fichiers_pages_utilises
                ],
                "affirmations": [
                    {
                        "affirmation": a["affirmation"],
                        "passage_id": a["passage_id"],
                        "fichier": a.get("fichier"),
                        "page": a["page"],
                        "citation": a["citation"],
                        "citation_presente": a["citation_presente"],
                        "preuve_supported": a["preuve_supported"],
                        "affirmation_validee": a["affirmation_validee"],
                    }
                    for a in affirmations
                ],
                "temps_indexation_secondes": temps_indexation,
                "temps_recherche_secondes": temps_recherche,
                "temps_generation_secondes": temps_generation,
            }
        )

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(resultats_tests, f, ensure_ascii=False, indent=2)
    print(f"Résultats enregistrés dans {RESULTS_PATH}")


if __name__ == "__main__":
    main()
