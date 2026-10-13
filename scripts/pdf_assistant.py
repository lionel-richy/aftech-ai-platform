"""
Assistant documentaire AFTECH — version PDF.

Même principe que scripts/document_assistant.py (RAG : Retrieval-Augmented
Generation), mais la source de connaissance est ici un unique fichier PDF
au lieu de plusieurs petits fichiers .txt.

Cette version ajoute deux garde-fous supplémentaires par rapport à une
recherche + génération classique :
1) la réponse de Qwen est découpée en "affirmations" indépendantes, chacune
   avec sa propre preuve (passage + page + citation) ;
2) chaque affirmation doit passer DEUX vérifications avant d'être acceptée :
   la citation existe-t-elle vraiment dans le passage désigné, ET un second
   appel à Qwen (qui ne voit que la question, l'affirmation et la citation,
   pas le document) confirme-t-il que la citation prouve l'affirmation.
Une affirmation qui échoue à l'un des deux tests est supprimée.
"""

import json
import os
import re
import unicodedata

import torch
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer, util
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# Le PDF est déjà présent sur la machine Colab à ce chemin
PDF_PATH = "/content/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"

RESULTS_PATH = "results/benchmarks/pdf_rag_test.json"

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# Découpage des pages en passages : une page peut être longue, on la coupe
# en morceaux plus digestes pour la recherche de similarité.
TAILLE_PASSAGE = 800  # nombre de caractères par passage (environ)
CHEVAUCHEMENT = 150  # caractères communs entre deux passages consécutifs

# Recherche en deux temps : on remonte large avec la similarité sémantique
# seule, puis on affine avec un bonus lexical avant de garder le top final.
TOP_K_INITIAL = 10  # passages remontés par la seule similarité sémantique (BGE-M3), par requête
TOP_K_FINAL = 5  # passages conservés après combinaison sémantique + lexicale (questions SIMPLE)
TOP_K_LISTE_MAX = 12  # nombre maximal de passages envoyés à Qwen pour une question LISTE
BONUS_PAR_MOT = 0.05  # bonus ajouté par mot important trouvé exactement dans le passage

# Mots trop courants pour être utiles à la recherche lexicale : on les ignore
# quand on extrait les "mots importants" de la question.
MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "est", "quel", "quelle"}

# Mots qui trahissent une question demandant PLUSIEURS éléments (liste, étapes,
# chantiers, recommandations...) plutôt qu'une information précise unique.
MOTS_CLES_LISTE = [
    "quels sont",
    "quelles sont",
    "liste",
    "étapes",
    "chantiers",
    "recommandations",
    "éléments",
    "points",
]

NB_REFORMULATIONS = 3  # nombre de reformulations alternatives générées pour une question LISTE
SEUIL_STATUT_COMPLETE = 3  # nombre d'affirmations validées à partir duquel une liste est "complète"

REPONSE_NON_TROUVEE = "Information non trouvée dans le document."

MAX_NEW_TOKENS = 400  # laisse de la place aux réponses de type liste (plusieurs affirmations)
CITATION_MAX_CARACTERES = 200  # longueur maximale demandée pour une citation

# Termes clés dont on veut savoir, indépendamment des questions posées, où ils
# apparaissent dans le document (sert à vérifier que le découpage/l'extraction
# du PDF n'a pas "perdu" une information importante).
TERMES_DIAGNOSTIC = ["vLLM", "moteur central", "Concevoir la plateforme"]

# Message système : on force Qwen à ne s'appuyer que sur les passages fournis
# (identifiés P1 à P5), et à découper sa réponse en affirmations, chacune
# justifiée par une preuve précise (passage + page + citation).
SYSTEM_PROMPT = (
    "Tu es un assistant documentaire. Tu réponds toujours en français. Tu dois "
    "répondre UNIQUEMENT à partir des passages fournis dans le message de "
    "l'utilisateur, identifiés par P1, P2, P3, P4, P5. Ne complète jamais avec "
    "tes connaissances générales, même si tu penses connaître la réponse.\n\n"
    "Si les passages ne contiennent pas clairement la réponse, réponds "
    f'uniquement avec la phrase exacte : "{REPONSE_NON_TROUVEE}" (rien d\'autre).\n\n'
    "Sinon, découpe ta réponse en affirmations séparées : une seule affirmation "
    "pour une réponse simple, ou une affirmation distincte par élément si la "
    "réponse est une liste (6 éléments maximum). Pour CHAQUE affirmation, utilise "
    "STRICTEMENT ce format, sur 4 lignes :\n"
    "AFFIRMATION: <une seule affirmation, phrase complète>\n"
    "PASSAGE: <identifiant, ex. P2>\n"
    "PAGE: <numéro de page>\n"
    f'CITATION: "<citation copiée EXACTEMENT depuis ce passage, {CITATION_MAX_CARACTERES} '
    'caractères maximum>"\n\n'
    "Répète ce bloc de 4 lignes pour chaque affirmation. Termine toujours tes phrases "
    "(n'écris jamais une phrase coupée)."
)

# Le vérificateur ne voit JAMAIS le document : seulement la question,
# l'affirmation, et la citation censée la prouver. C'est un second avis
# indépendant, pas une simple relecture du premier raisonnement de Qwen.
VERIFICATEUR_SYSTEM_PROMPT = (
    "Tu es un vérificateur strict. Tu reçois une question, une affirmation et une "
    "citation censée prouver cette affirmation. Réponds par un seul mot : "
    "SUPPORTED si la citation prouve clairement l'affirmation pour cette question, "
    "ou NOT_SUPPORTED si ce n'est pas le cas ou si c'est ambigu. N'écris rien d'autre."
)

# Pour les questions LISTE : on ne demande PAS de réponse à ce stade, seulement
# des reformulations utiles pour retrouver davantage de passages pertinents
# (une liste ou un tableau est souvent dispersé sur plusieurs formulations).
REFORMULATION_SYSTEM_PROMPT = (
    "Tu aides à améliorer une recherche documentaire. On te donne une question. "
    "Propose 3 reformulations différentes de cette question, avec d'autres mots, "
    "pour retrouver davantage de passages pertinents dans un document. Ne réponds "
    "PAS à la question : donne uniquement les 3 reformulations, une par ligne, "
    "sans numérotation ni commentaire."
)

# Questions posées automatiquement à la fin du script.
# La dernière ("directeur financier") teste volontairement une information
# qui n'existe probablement pas dans ce document technique.
QUESTIONS = [
    "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
    "Quel runtime LLM principal est recommandé ?",
    "Quels sont les grands chantiers couverts par cette Epic ?",
    "Quel est le nom du directeur financier d'AFTECH ?",
]


def decouper_texte(texte, taille=TAILLE_PASSAGE, chevauchement=CHEVAUCHEMENT):
    """Découpe un long texte en passages de taille fixe, avec chevauchement.

    Le chevauchement évite qu'une phrase importante soit coupée en deux et
    perde tout son sens si elle tombe pile à la frontière entre deux passages.
    """
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def charger_passages_pdf():
    """Lit le PDF page par page et le découpe en passages.

    Pour chaque passage, on garde le nom du PDF et le numéro réel de la page
    (en commençant à 1) : c'est ce qui permettra plus tard de dire
    précisément "la réponse vient de la page X".
    """
    nom_pdf = os.path.basename(PDF_PATH)
    lecteur = PdfReader(PDF_PATH)

    passages = []  # texte de chaque passage
    pages = []  # numéro de page correspondant (même index que "passages")

    for indice_page, page in enumerate(lecteur.pages):
        numero_page = indice_page + 1  # les pages humaines commencent à 1, pas à 0
        texte_page = page.extract_text() or ""

        for morceau in decouper_texte(texte_page):
            passages.append(morceau)
            pages.append(numero_page)

    return nom_pdf, passages, pages


def extraire_mots_importants(question):
    """Retire les mots trop courants d'une question pour ne garder que les mots porteurs de sens."""
    mots = re.findall(r"\w+", question.lower(), re.UNICODE)
    return [mot for mot in mots if mot not in MOTS_VIDES and len(mot) > 1]


def calculer_bonus_lexical(mots_importants, texte_passage):
    """Ajoute un bonus par mot important de la question trouvé EXACTEMENT dans le passage.

    Ce bonus complète le score sémantique (BGE-M3) : le sens peut être proche
    sans que le mot exact y soit, et inversement un mot exact rare (ex. un nom
    propre ou un terme technique comme "vLLM") est un signal fort que le score
    sémantique seul peut sous-estimer.
    """
    texte_lower = texte_passage.lower()
    nb_trouves = sum(
        1 for mot in mots_importants if re.search(rf"\b{re.escape(mot)}\b", texte_lower)
    )
    return nb_trouves * BONUS_PAR_MOT


def classifier_question(question):
    """Distingue une question SIMPLE (une information précise) d'une question
    LISTE (plusieurs éléments, étapes, chantiers ou recommandations attendus).

    Règle simple basée sur des mots-clés : pas besoin d'appeler Qwen pour ça,
    la formulation de la question suffit dans la grande majorité des cas.
    """
    question_normalisee = question.lower()
    if any(mot_cle in question_normalisee for mot_cle in MOTS_CLES_LISTE):
        return "LISTE"
    return "SIMPLE"


def rechercher_candidats(question, embedder, embeddings_passages, passages, top_k=TOP_K_INITIAL):
    """Cherche, pour UNE formulation de question, les passages les plus proches
    sémantiquement (BGE-M3), puis ajoute à chacun son bonus lexical.

    Renvoie une liste de candidats identifiés par leur indice dans la liste
    globale "passages" (pas encore de "P1, P2..." à ce stade : ça viendra
    après la fusion entre plusieurs formulations, pour une question LISTE).
    """
    embedding_question = embedder.encode(question, convert_to_tensor=True)
    scores_semantiques = util.cos_sim(embedding_question, embeddings_passages)[0]

    nb = min(top_k, len(passages))
    indices = torch.topk(scores_semantiques, k=nb).indices.tolist()
    mots_importants = extraire_mots_importants(question)

    candidats = []
    for indice in indices:
        score_semantique = float(scores_semantiques[indice])
        bonus_lexical = calculer_bonus_lexical(mots_importants, passages[indice])
        candidats.append(
            {
                "indice": indice,
                "score_semantique": score_semantique,
                "bonus_lexical": bonus_lexical,
                "score_final": score_semantique + bonus_lexical,
            }
        )
    return candidats


def generer_reformulations(question, tokenizer, model):
    """Demande à Qwen 3 reformulations de la question, UNIQUEMENT pour élargir
    la recherche (Qwen ne répond pas à la question à ce stade)."""
    messages = [
        {"role": "system", "content": REFORMULATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question : {question}"},
    ]
    texte_brut = generer_texte(messages, tokenizer, model, max_new_tokens=150)

    reformulations = []
    for ligne in texte_brut.splitlines():
        ligne = re.sub(r"^[\s\-\*\d\.\)]+", "", ligne).strip()
        if ligne:
            reformulations.append(ligne)

    return reformulations[:NB_REFORMULATIONS]


def _passage_depuis_candidat(rang, indice, candidat, passages, pages, nom_pdf):
    """Construit le dict final d'un passage (avec son identifiant Pn) à partir
    d'un candidat identifié par son indice dans la liste globale des passages."""
    return {
        "id": f"P{rang + 1}",
        "texte": passages[indice],
        "page": pages[indice],
        "pdf": nom_pdf,
        "score_semantique": candidat["score_semantique"],
        "bonus_lexical": candidat["bonus_lexical"],
        "score_final": candidat["score_final"],
    }


def recuperer_passages(question, embedder, embeddings_passages, passages, pages, nom_pdf):
    """Retrouve les TOP_K_FINAL meilleurs passages pour une question SIMPLE :
    une seule recherche, triée sur le score sémantique + bonus lexical combinés."""
    candidats = rechercher_candidats(question, embedder, embeddings_passages, passages)
    candidats.sort(key=lambda c: c["score_final"], reverse=True)
    meilleurs = candidats[:TOP_K_FINAL]

    return [
        _passage_depuis_candidat(rang, c["indice"], c, passages, pages, nom_pdf)
        for rang, c in enumerate(meilleurs)
    ]


def rechercher_passages_liste(
    question, reformulations, embedder, embeddings_passages, passages, pages, nom_pdf
):
    """Recherche élargie pour une question LISTE :

    1) interroge la question originale + ses reformulations ;
    2) fusionne les résultats en supprimant les doublons (on garde le
       meilleur score vu pour chaque passage) ;
    3) ajoute le passage précédent et le passage suivant de chaque passage
       retenu, seulement s'ils sont sur la même page (pour ne pas couper un
       tableau ou une liste à cheval sur deux passages) ;
    4) limite le tout à TOP_K_LISTE_MAX passages avant de les envoyer à Qwen.
    """
    # Étape 1 + 2 : fusion et dédoublonnage sur toutes les formulations
    meilleur_candidat_par_indice = {}
    for formulation in [question] + reformulations:
        for candidat in rechercher_candidats(formulation, embedder, embeddings_passages, passages):
            indice = candidat["indice"]
            existant = meilleur_candidat_par_indice.get(indice)
            if existant is None or candidat["score_final"] > existant["score_final"]:
                meilleur_candidat_par_indice[indice] = candidat

    # Étape 3 : expansion par voisinage (page précédente/suivante identique)
    candidats_etendus = dict(meilleur_candidat_par_indice)
    for indice, candidat in list(meilleur_candidat_par_indice.items()):
        for indice_voisin in (indice - 1, indice + 1):
            deja_present = indice_voisin in candidats_etendus
            dans_les_limites = 0 <= indice_voisin < len(passages)
            if not dans_les_limites or deja_present:
                continue
            if pages[indice_voisin] != pages[indice]:
                continue
            # Le voisin est ajouté pour le contexte (reconstituer un tableau/une
            # liste coupée), pas parce qu'il a été jugé pertinent lui-même :
            # il hérite d'un score légèrement inférieur à son passage d'origine.
            candidats_etendus[indice_voisin] = {
                "indice": indice_voisin,
                "score_semantique": 0.0,
                "bonus_lexical": 0.0,
                "score_final": candidat["score_final"] * 0.99,
            }

    # Étape 4 : on garde les TOP_K_LISTE_MAX meilleurs scores...
    candidats_tries = sorted(candidats_etendus.values(), key=lambda c: c["score_final"], reverse=True)
    meilleurs = candidats_tries[:TOP_K_LISTE_MAX]
    # ...puis on les remet dans l'ordre de lecture du document : plus facile
    # pour Qwen de reconstituer un tableau/une liste dans le bon ordre.
    meilleurs.sort(key=lambda c: c["indice"])

    return [
        _passage_depuis_candidat(rang, c["indice"], c, passages, pages, nom_pdf)
        for rang, c in enumerate(meilleurs)
    ]


def construire_prompt(question, passages):
    """Construit le contexte (passages identifiés + numéro de page) envoyé à Qwen."""
    contexte = "\n\n".join(f"[{p['id']} | page {p['page']}] {p['texte']}" for p in passages)
    return f"Passages du document :\n{contexte}\n\nQuestion : {question}"


# Caractères Unicode invisibles à supprimer (trait d'union invisible, espaces
# et joints de largeur nulle) : la mise en page d'un PDF en ajoute souvent
# sans qu'on les voie, ce qui peut faire échouer une comparaison de texte
# par ailleurs correcte.
CARACTERES_INVISIBLES = "­​‌‍⁠﻿"


def normalize_text(texte):
    """Normalise un texte pour pouvoir comparer citation et passage de façon fiable.

    Étapes, dans l'ordre :
    1) unicodedata.normalize("NFKC", ...) : uniformise les variantes Unicode
       d'un même caractère (ex. ligature "ﬁ" -> "fi").
    2) espaces insécables -> espace normal.
    3) traits d'union invisibles / caractères de largeur nulle -> supprimés.
    4) séquence littérale "\\n" (backslash + n, pas un vrai saut de ligne,
       qui peut apparaître si Qwen écrit l'échappement en toutes lettres)
       -> remplacée par un espace.
    5) vrais retours à la ligne / tabulations -> espace.
    6) espaces successifs réduits à un seul, espaces de bord retirés.
    7) minuscules (uniquement pour la comparaison, pas pour l'affichage).
    """
    texte = unicodedata.normalize("NFKC", texte)
    texte = texte.replace(" ", " ").replace(" ", " ")

    for caractere in CARACTERES_INVISIBLES:
        texte = texte.replace(caractere, "")

    texte = texte.replace("\\n", " ")
    texte = texte.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texte = " ".join(texte.split())

    return texte.lower()


def afficher_diagnostic_termes(passages, pages):
    """Affiche, indépendamment des questions posées, où se trouvent des termes clés.

    Sert à vérifier que le découpage en passages n'a pas "coupé" ou perdu une
    information importante quelque part dans le document.
    """
    print("=== Diagnostic : recherche de termes clés dans le document ===")
    for terme in TERMES_DIAGNOSTIC:
        terme_normalise = normalize_text(terme)
        print(f'Terme recherché : "{terme}"')
        trouve = False
        for indice, texte in enumerate(passages):
            if terme_normalise in normalize_text(texte):
                trouve = True
                extrait = texte[:120].replace("\n", " ")
                print(f"  - page {pages[indice]} : {extrait}...")
        if not trouve:
            print("  (aucune occurrence trouvée)")
    print()


# Un bloc d'affirmation ressemble à :
# AFFIRMATION: <texte>
# PASSAGE: P2
# PAGE: 6
# CITATION: "texte copié depuis le passage"
PATTERN_AFFIRMATION = re.compile(
    r"AFFIRMATION\s*:\s*(?P<affirmation>.+?)\s*"
    r"PASSAGE\s*:\s*(?P<passage_id>\S+)\s*"
    r"PAGE\s*:\s*(?P<page>\d+)\s*"
    r'CITATION\s*:\s*"(?P<citation>.+?)"',
    re.IGNORECASE | re.DOTALL,
)


def parser_affirmations(texte_brut):
    """Extrait la liste des affirmations (avec leur preuve) du format structuré.

    Renvoie une liste de dicts {"affirmation", "passage_id", "page", "citation"}.
    Une liste vide signifie que Qwen n'a fourni aucune affirmation structurée
    (typiquement parce qu'il a répondu directement par la phrase "non trouvée").
    """
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
    """Première vérification : la citation existe-t-elle mot pour mot dans le PASSAGE COMPLET ?

    Important : on compare au passage entier réellement envoyé à Qwen, jamais
    à un extrait tronqué — sinon une citation correcte mais absente de
    l'extrait serait rejetée à tort.
    """
    if not passage or not citation.strip():
        return False
    return normalize_text(citation) in normalize_text(passage["texte"])


def generer_texte(messages, tokenizer, model, max_new_tokens):
    """Envoie des messages à Qwen et renvoie le texte généré (utilitaire commun
    à la génération de réponse et à la vérification)."""
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
    """Deuxième vérification, indépendante de la première : on redemande à Qwen,
    SANS lui redonner le document, si la citation prouve vraiment l'affirmation.

    Le vérificateur ne reçoit que la question, l'affirmation et la citation —
    jamais le passage complet ni les autres passages — pour juger uniquement
    si la preuve avancée tient debout, sans pouvoir "retrouver" la réponse
    ailleurs dans le document.
    """
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

    # On teste NOT_SUPPORTED en premier : la sous-chaîne "SUPPORTED" est aussi
    # présente dans "NOT_SUPPORTED", donc l'ordre du test compte.
    if "NOT_SUPPORTED" in verdict_brut:
        return False
    return "SUPPORTED" in verdict_brut


def main():
    # --- Étape 1 : lecture et découpage du PDF (partie "Retrieval") ---
    print(f"Lecture du PDF : {PDF_PATH}")
    nom_pdf, passages, pages = charger_passages_pdf()
    print(f"{len(passages)} passages extraits sur {len(set(pages))} pages.\n")

    afficher_diagnostic_termes(passages, pages)

    print(f"Chargement du modèle d'embeddings {EMBEDDING_MODEL_NAME} sur CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Calcul des embeddings de tous les passages...\n")
    embeddings_passages = embedder.encode(passages, convert_to_tensor=True)

    # --- Étape 2 : préparation du modèle de génération (partie "Generation") ---
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
    resultats_tests = []

    for question in QUESTIONS:
        print("=" * 70)
        print(f"Question : {question}")

        type_question = classifier_question(question)
        print(f"Type de question : {type_question}\n")

        if type_question == "LISTE":
            reformulations = generer_reformulations(question, tokenizer, model)
            print("Reformulations utilisées pour élargir la recherche :")
            for reformulation in reformulations:
                print(f"  - {reformulation}")
            print()
            passages_trouves = rechercher_passages_liste(
                question, reformulations, embedder, embeddings_passages, passages, pages, nom_pdf
            )
        else:
            reformulations = []
            passages_trouves = recuperer_passages(
                question, embedder, embeddings_passages, passages, pages, nom_pdf
            )

        pages_utilisees = sorted({p["page"] for p in passages_trouves})

        # Dictionnaire pour retrouver le passage COMPLET à partir de son identifiant
        # (P1, P2, ...) : c'est ce texte complet qui sert à valider les citations,
        # pas le court extrait affiché ci-dessous.
        passages_par_id = {p["id"]: p for p in passages_trouves}

        print(f"PDF : {nom_pdf}")
        print(f"Pages utilisées : {pages_utilisees}")
        print("Passages retrouvés (score sémantique, bonus lexical, score final) :")
        for p in passages_trouves:
            extrait = p["texte"][:120].replace("\n", " ")
            print(
                f"  - {p['id']} | page {p['page']} | "
                f"sémantique={p['score_semantique']:.3f} | "
                f"bonus={p['bonus_lexical']:.3f} | "
                f"final={p['score_final']:.3f} : {extrait}..."
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": construire_prompt(question, passages_trouves)},
        ]
        reponse_brute = generer_texte(messages, tokenizer, model, MAX_NEW_TOKENS)

        affirmations = parser_affirmations(reponse_brute)

        # Pour chaque affirmation : deux vérifications indépendantes.
        for aff in affirmations:
            passage = passages_par_id.get(aff["passage_id"])
            aff["citation_presente"] = citation_est_presente(aff["citation"], passage)

            # Pas la peine d'appeler Qwen une seconde fois si la citation
            # n'existe déjà pas dans le passage : l'affirmation est de toute
            # façon rejetée (les deux conditions sont obligatoires).
            if aff["citation_presente"]:
                aff["preuve_supported"] = verifier_affirmation(
                    question, aff["affirmation"], aff["citation"], tokenizer, model
                )
            else:
                aff["preuve_supported"] = False

            aff["affirmation_validee"] = aff["citation_presente"] and aff["preuve_supported"]

        affirmations_gardees = [a for a in affirmations if a["affirmation_validee"]]

        if not affirmations_gardees:
            # Aucune affirmation n'a résisté aux deux vérifications : on ne
            # garde rien plutôt que de risquer d'afficher une information fausse.
            reponse_finale = REPONSE_NON_TROUVEE
        elif len(affirmations_gardees) == 1:
            reponse_finale = affirmations_gardees[0]["affirmation"]
        else:
            reponse_finale = "\n".join(f"- {a['affirmation']}" for a in affirmations_gardees)

        # Statut final : uniquement informatif pour une question SIMPLE (une
        # seule affirmation possible), mais utile pour une question LISTE afin
        # de savoir si la liste reconstituée est probablement complète.
        nb_validees = len(affirmations_gardees)
        if nb_validees == 0:
            statut = "NOT_FOUND"
        elif type_question == "LISTE" and nb_validees < SEUIL_STATUT_COMPLETE:
            statut = "PARTIAL"
        else:
            statut = "COMPLETE"

        print(f"\nRéponse : {reponse_finale}")
        print(f"Statut : {statut}")
        if statut == "PARTIAL":
            print("Réponse partielle : certains éléments peuvent manquer.")
        print("Affirmations :")
        if affirmations:
            for a in affirmations:
                statut_affirmation = "validée" if a["affirmation_validee"] else "SUPPRIMÉE"
                print(
                    f"  - [{statut_affirmation}] {a['affirmation']!r} "
                    f"({a['passage_id']}, page {a['page']}) "
                    f"citation_presente={a['citation_presente']} "
                    f"preuve_supported={a['preuve_supported']}"
                )
        else:
            print("  (aucune)")
        print()

        resultats_tests.append(
            {
                "question": question,
                "type_question": type_question,
                "statut": statut,
                "reponse": reponse_finale,
                "pdf": nom_pdf,
                "pages": pages_utilisees,
                "reformulations": reformulations,
                "affirmations": [
                    {
                        "affirmation": a["affirmation"],
                        "passage_id": a["passage_id"],
                        "page": a["page"],
                        "citation": a["citation"],
                        "citation_presente": a["citation_presente"],
                        "preuve_supported": a["preuve_supported"],
                        "affirmation_validee": a["affirmation_validee"],
                    }
                    for a in affirmations
                ],
            }
        )

    # --- Étape 4 : sauvegarde des résultats ---
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(resultats_tests, f, ensure_ascii=False, indent=2)
    print(f"Résultats enregistrés dans {RESULTS_PATH}")


if __name__ == "__main__":
    main()
