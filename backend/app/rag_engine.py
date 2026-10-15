"""Moteur RAG multi-PDF, utilisé par l'API FastAPI.

Reprend EXACTEMENT le mécanisme de sécurité validé dans
scripts/query_document_index.py (affirmations + double vérification
citation-présente / SUPPORTED-NOT_SUPPORTED), refactoré en classe pour :
- charger l'index, l'embedder et Qwen UNE SEULE FOIS par conteneur
  (appelé depuis le "lifespan" de FastAPI, voir main.py) ;
- répondre à plusieurs questions sans recharger quoi que ce soit ;
- se comporter proprement en l'ABSENCE de GPU (ex. sur ce Mac, qui n'a pas
  de CUDA) : le moteur reste "degraded" plutôt que de planter, ce qui donne
  le scénario "backend indisponible" testé dans tests/test_backend_unavailable.py.
"""

import json
import os
import re
import threading
import unicodedata
from typing import Optional

INDEX_DIR_DEFAULT = os.environ.get("INDEX_DIR", "data/indexes/aftech_documents")

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

MAX_NEW_TOKENS = 400
CITATION_MAX_CARACTERES = 200

LANGUES_SUPPORTEES = ("fr", "en", "de")

# Une phrase "non trouvée" par langue de réponse (response_language) — jamais
# une traduction automatique à la volée : le texte est fixe et validé pour
# chaque langue, comme REPONSE_NON_TROUVEE l'était déjà pour le français.
REPONSE_NON_TROUVEE_PAR_LANGUE = {
    "fr": "Information non trouvée dans les documents.",
    "en": "Information not found in the documents.",
    "de": "Information in den Dokumenten nicht gefunden.",
}
REPONSE_NON_TROUVEE = REPONSE_NON_TROUVEE_PAR_LANGUE["fr"]

# Suffixe "[source : fichier, page N]" ajouté après chaque affirmation
# validée — jamais traduit : fichier et libellé de page restent neutres/
# fidèles à la source, seul le connecteur ("source"/"source"/"Quelle") change.
SOURCE_SUFFIXE_PAR_LANGUE = {
    "fr": "[source : {fichier}, page {page}]",
    "en": "[source: {fichier}, page {page}]",
    "de": "[Quelle: {fichier}, Seite {page}]",
}

NOM_LANGUE_PAR_CODE = {"fr": "français", "en": "English", "de": "Deutsch"}

SEUIL_STATUT_COMPLETE = 3


def construire_system_prompt(langue: str) -> str:
    """Prompt système, paramétré par la langue de RÉPONSE demandée.

    La CITATION doit toujours rester une copie exacte du passage source, donc
    dans sa langue D'ORIGINE, même quand la langue de réponse diffère — c'est
    explicite ci-dessous pour éviter que Qwen ne "traduise" une citation."""
    nom_langue = NOM_LANGUE_PAR_CODE[langue]
    reponse_non_trouvee = REPONSE_NON_TROUVEE_PAR_LANGUE[langue]
    return (
        f"Tu es un assistant documentaire. Tu réponds TOUJOURS en {nom_langue}, "
        "quelle que soit la langue des passages fournis ou de la question : "
        "traduis le SENS de ta réponse (l'AFFIRMATION) en cette langue si "
        "besoin. Les passages fournis peuvent provenir de documents "
        "différents et sont identifiés par P1, P2, P3, etc. Tu dois répondre "
        "UNIQUEMENT à partir de ces passages. Ne complète jamais avec tes "
        "connaissances générales, même si tu penses connaître la réponse.\n\n"
        "Si les passages ne contiennent pas clairement la réponse, réponds "
        f'uniquement avec la phrase exacte : "{reponse_non_trouvee}" (rien d\'autre).\n\n'
        "Sinon, découpe ta réponse en affirmations séparées : une seule affirmation "
        "pour une réponse simple, ou une affirmation distincte par élément si la "
        "réponse est une liste ou une synthèse à plusieurs points (6 éléments "
        "maximum). Pour CHAQUE affirmation, utilise STRICTEMENT ce format, sur 4 "
        "lignes :\n"
        f"AFFIRMATION: <une seule affirmation, phrase complète, en {nom_langue}>\n"
        "PASSAGE: <identifiant, ex. P2>\n"
        "PAGE: <numéro de page>\n"
        f'CITATION: "<citation copiée EXACTEMENT depuis ce passage, dans sa langue '
        f"D'ORIGINE (ne la traduis jamais), {CITATION_MAX_CARACTERES} "
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


# Conservé pour compatibilité (tests existants, scripts) : prompt par défaut
# en français — identique à construire_system_prompt("fr").
SYSTEM_PROMPT = construire_system_prompt("fr")

VERIFICATEUR_SYSTEM_PROMPT = (
    "Tu es un vérificateur strict. Tu reçois une question, une affirmation et une "
    "citation censée prouver cette affirmation. Réponds par un seul mot : "
    "SUPPORTED si la citation prouve clairement l'affirmation pour cette question, "
    "ou NOT_SUPPORTED si ce n'est pas le cas ou si c'est ambigu. N'écris rien d'autre."
)

CARACTERES_INVISIBLES = "­​‌‍⁠﻿"


def normalize_text(texte: str) -> str:
    """Identique à scripts/pdf_assistant.py / query_document_index.py :
    NFKC, espaces insécables, caractères invisibles, séquences "\\n"
    littérales et vrais retours à la ligne, espaces multiples, minuscules."""
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


def parser_affirmations(texte_brut: str) -> list[dict]:
    return [
        {
            "affirmation": m.group("affirmation").strip(),
            "passage_id": m.group("passage_id").strip().upper(),
            "page": int(m.group("page")),
            "citation": m.group("citation").strip(),
        }
        for m in PATTERN_AFFIRMATION.finditer(texte_brut)
    ]


class BackendUnavailable(Exception):
    """Le moteur RAG ne peut pas répondre (pas de GPU, modèle non chargé,
    index absent). Traduit en HTTP 503 par l'API — jamais une 500 opaque."""


class RagEngine:
    def __init__(self, index_dir: str = INDEX_DIR_DEFAULT) -> None:
        self.index_dir = index_dir
        self.ready = False
        self.error: Optional[str] = None
        self.gpu_name = "indisponible"
        self.vram_totale_octets: Optional[int] = None

        self.index = None
        self.chunks: list[dict] = []
        self.manifest: dict = {}
        self.embedder = None
        self.tokenizer = None
        self.model = None

        # Temps de chargement par phase (secondes), rempli par _load_impl().
        # Réutilisé par scripts/gpu_benchmark.py pour éviter de dupliquer la
        # logique de chargement (donc : même code = même paramètres garantis
        # entre les GPU testés).
        self.timings_chargement: dict[str, float] = {}
        self._verrou_rechargement = threading.Lock()

    # --- Chargement (une seule fois par conteneur, voir main.py:lifespan) ---

    def load(self) -> None:
        """Ne lève JAMAIS d'exception : le serveur doit démarrer même si un
        paquet manque ou si l'index est absent, en passant en mode "degraded"
        avec un message clair (voir self.error) plutôt que de planter."""
        try:
            self._load_impl()
        except Exception as exc:  # noqa: BLE001 — volontaire, voir docstring
            self.error = f"Échec du chargement du moteur RAG : {exc}"
            self.ready = False

    def _load_impl(self) -> None:
        import time as _time

        import faiss

        debut = _time.perf_counter()
        try:
            self.index = faiss.read_index(os.path.join(self.index_dir, "index.faiss"))
            with open(os.path.join(self.index_dir, "chunks.json"), encoding="utf-8") as f:
                self.chunks = json.load(f)
            with open(os.path.join(self.index_dir, "manifest.json"), encoding="utf-8") as f:
                self.manifest = json.load(f)
        except FileNotFoundError as exc:
            self.error = f"Index introuvable dans {self.index_dir} : {exc}"
            return
        self.timings_chargement["index_secondes"] = _time.perf_counter() - debut

        import torch
        from sentence_transformers import SentenceTransformer

        debut = _time.perf_counter()
        self.embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
        self.timings_chargement["embedder_secondes"] = _time.perf_counter() - debut

        if not torch.cuda.is_available():
            self.error = (
                "Aucun GPU CUDA détecté sur cette machine : le modèle de génération "
                "(Qwen, quantifié 4 bits) ne peut pas être chargé ici. La recherche "
                "de documents et /health restent disponibles ; /ask renverra 503 "
                "jusqu'au déploiement sur une machine avec GPU (Modal)."
            )
            return

        self.gpu_name = torch.cuda.get_device_name(0)
        self.vram_totale_octets = torch.cuda.get_device_properties(0).total_memory

        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        if "T4" in self.gpu_name:
            compute_dtype = torch.float16
        elif torch.cuda.is_bf16_supported():
            compute_dtype = torch.bfloat16
        else:
            compute_dtype = torch.float16

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )

        debut = _time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL_NAME,
            quantization_config=quant_config,
            device_map="auto",
        )
        self.timings_chargement["llm_secondes"] = _time.perf_counter() - debut

        self.ready = True

    # --- État (utilisé par /health et /documents, jamais bloquant) ---

    def health(self) -> dict:
        vram_utilisee_octets = None
        if self.ready:
            import torch

            vram_utilisee_octets = torch.cuda.memory_allocated()

        return {
            "status": "ok" if self.ready else "degraded",
            "ready": self.ready,
            "llm_model": LLM_MODEL_NAME,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "gpu": self.gpu_name,
            "vram_totale_octets": self.vram_totale_octets,
            "vram_utilisee_octets": vram_utilisee_octets,
            "documents_count": len(self.manifest.get("pdf", [])),
            "chunks_count": len(self.chunks),
        }

    def recharger_index(self, dossier_index: str) -> None:
        """Remplace l'index/chunks/manifest ACTIFS par une version reconstruite
        avec succès (voir index_builder.reconstruire_index) — sans recharger
        Qwen ni BGE-M3, et sans redémarrer le conteneur. Les recherches déjà
        en cours au moment de l'appel continuent sur l'ancienne version (voir
        _rechercher_passages, qui capture ses propres références locales)."""
        import faiss

        nouvel_index = faiss.read_index(os.path.join(dossier_index, "index.faiss"))
        with open(os.path.join(dossier_index, "chunks.json"), encoding="utf-8") as f:
            nouveaux_chunks = json.load(f)
        with open(os.path.join(dossier_index, "manifest.json"), encoding="utf-8") as f:
            nouveau_manifest = json.load(f)

        with self._verrou_rechargement:
            self.index = nouvel_index
            self.chunks = nouveaux_chunks
            self.manifest = nouveau_manifest

    def chunks_historiques(self, noms_affiches_geres: set[str]) -> list[dict]:
        """Chunks actuellement actifs dont la source N'EST PAS gérée par le
        registre de documents (ex. les 4 PDF déjà indexés avant cette
        fonctionnalité, dont on n'a jamais eu le fichier d'origine sur ce
        volume) — à conserver tels quels lors d'une reconstruction, jamais
        ré-extraits puisqu'on ne possède pas leur PDF source."""
        return [c for c in self.chunks if c["source"] not in noms_affiches_geres]

    def documents(self) -> list[dict]:
        stats = self.manifest.get("stats_par_pdf", {})
        hashes = self.manifest.get("hashes_pdf", {})
        date_index = self.manifest.get("date_creation", "")
        modele = self.manifest.get("modele_embeddings", EMBEDDING_MODEL_NAME)

        return [
            {
                "nom_fichier": nom,
                "pages": stats.get(nom, {}).get("pages", 0),
                "passages": stats.get(nom, {}).get("passages", 0),
                "hash_sha256": hashes.get(nom, ""),
                "modele_embeddings": modele,
                "date_index": date_index,
            }
            for nom in self.manifest.get("pdf", [])
        ]

    # --- Recherche + génération ---

    def _rechercher_passages(self, question: str, top_k: int) -> list[dict]:
        # Références LOCALES capturées une seule fois : si recharger_index()
        # remplace self.index/self.chunks pendant cette recherche (ajout de
        # document depuis la Bibliothèque), cet appel continue d'utiliser la
        # version qu'il a capturée au début, jamais un mélange des deux.
        index, chunks = self.index, self.chunks

        embedding_question = self.embedder.encode(
            [question], convert_to_numpy=True, normalize_embeddings=True
        ).astype("float32")

        nb = min(top_k, len(chunks))
        if nb == 0:
            # Bibliothèque vide (tous les documents supprimés) : FAISS refuse
            # k=0 (AssertionError), donc on court-circuite plutôt que
            # d'interroger un index sans aucun vecteur.
            return []
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

    def _construire_prompt(self, question: str, passages: list[dict]) -> str:
        contexte = "\n\n".join(
            f"[{p['id']} | fichier {p['source']} | page {p['page']}] {p['texte']}" for p in passages
        )
        return f"Passages :\n{contexte}\n\nQuestion : {question}"

    def _generer_texte(self, messages: list[dict], max_new_tokens: int) -> tuple[str, int, int]:
        """Renvoie (texte_généré, nb_tokens_entrée, nb_tokens_générés).

        Les compteurs de tokens sont exposés pour le benchmark GPU
        (scripts/gpu_benchmark.py) ; main.py les ignore simplement (Pydantic
        ne garde que les champs déclarés dans AskResponse)."""
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)

        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

        nb_tokens_entree = inputs["input_ids"].shape[-1]
        generated_ids = output_ids[0][nb_tokens_entree:]
        texte = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        return texte, nb_tokens_entree, len(generated_ids)

    def _verifier_affirmation(self, question: str, affirmation: str, citation: str) -> bool:
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
        verdict_brut, _, _ = self._generer_texte(messages, max_new_tokens=10)
        verdict_brut = verdict_brut.strip().upper()

        if "NOT_SUPPORTED" in verdict_brut:
            return False
        return "SUPPORTED" in verdict_brut

    def ask(self, question: str, top_k: int = 8, response_language: str = "fr") -> dict:
        if not self.ready:
            raise BackendUnavailable(self.error or "Moteur RAG non prêt.")
        if response_language not in LANGUES_SUPPORTEES:
            raise ValueError(f"Langue de réponse non supportée : {response_language!r}")

        import time

        debut_recherche = time.perf_counter()
        passages = self._rechercher_passages(question, top_k)
        temps_recherche = time.perf_counter() - debut_recherche

        passages_par_id = {p["id"]: p for p in passages}

        debut_generation = time.perf_counter()
        messages = [
            {"role": "system", "content": construire_system_prompt(response_language)},
            {"role": "user", "content": self._construire_prompt(question, passages)},
        ]
        reponse_brute, nb_tokens_entree, nb_tokens_generes = self._generer_texte(messages, MAX_NEW_TOKENS)

        affirmations = parser_affirmations(reponse_brute)
        for aff in affirmations:
            passage = passages_par_id.get(aff["passage_id"])
            citation_presente = bool(passage) and bool(aff["citation"].strip())
            if citation_presente:
                citation_presente = normalize_text(aff["citation"]) in normalize_text(passage["texte"])

            aff["citation_presente"] = citation_presente
            aff["preuve_supported"] = (
                self._verifier_affirmation(question, aff["affirmation"], aff["citation"])
                if citation_presente
                else False
            )
            aff["affirmation_validee"] = aff["citation_presente"] and aff["preuve_supported"]

            # Fichier/page à partir de NOS métadonnées de recherche, jamais du
            # texte généré par Qwen : on ne lui fait pas confiance sur ce point.
            aff["fichier"] = passage["source"] if passage else None
            aff["page"] = passage["page"] if passage else aff["page"]

        temps_generation = time.perf_counter() - debut_generation

        validees = [a for a in affirmations if a["affirmation_validee"]]
        suffixe_source = SOURCE_SUFFIXE_PAR_LANGUE[response_language]

        if not validees:
            answer = REPONSE_NON_TROUVEE_PAR_LANGUE[response_language]
            statut = "NOT_FOUND"
        elif len(validees) == 1:
            a = validees[0]
            answer = f"{a['affirmation']} {suffixe_source.format(fichier=a['fichier'], page=a['page'])}"
            statut = "COMPLETE"
        else:
            answer = "\n".join(
                f"- {a['affirmation']} {suffixe_source.format(fichier=a['fichier'], page=a['page'])}"
                for a in validees
            )
            statut = "COMPLETE" if len(validees) >= SEUIL_STATUT_COMPLETE else "PARTIAL"

        sources = [
            {
                "fichier": p["source"],
                "page": p["page"],
                "extrait": p["texte"][:200],
                "score": p["score"],
            }
            for p in passages
        ]

        return {
            "answer": answer,
            "status": statut,
            "sources": sources,
            "validated_claims": [
                {
                    "affirmation": a["affirmation"],
                    "fichier": a["fichier"],
                    "page": a["page"],
                    "citation": a["citation"],
                    "citation_presente": a["citation_presente"],
                    "preuve_supported": a["preuve_supported"],
                }
                for a in validees
            ],
            "timings": {
                "recherche_secondes": temps_recherche,
                "generation_secondes": temps_generation,
                "total_secondes": temps_recherche + temps_generation,
            },
            # Champs additifs (pas dans AskResponse -> ignorés par l'API,
            # utilisés par scripts/gpu_benchmark.py).
            "tokens_entree": nb_tokens_entree,
            "tokens_generes": nb_tokens_generes,
        }


# --- Singleton protégé par verrou : empêche deux chargements simultanés ---
# (exigence explicite : "empêcher deux chargements simultanés du modèle").
# En pratique, c'est surtout le "lifespan" de FastAPI (voir main.py) qui
# appelle load() une seule fois ; ce verrou protège contre un double appel
# accidentel (ex. tests, rechargement à chaud en dev).
_engine: Optional[RagEngine] = None
_engine_lock = threading.Lock()


def get_engine(index_dir: str = INDEX_DIR_DEFAULT) -> RagEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                engine = RagEngine(index_dir)
                engine.load()
                _engine = engine
    return _engine


def reset_engine_for_tests() -> None:
    """Réservé aux tests : force un nouvel appel à get_engine() de repartir à zéro."""
    global _engine
    _engine = None
