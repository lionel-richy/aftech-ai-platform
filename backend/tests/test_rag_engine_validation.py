"""Tests de non-régression pour le mécanisme de validation du RagEngine.

Contexte : un faux NOT_FOUND a été observé en production pour la question
"Quel document contient des informations relatives à Azure ?" — la recherche
retrouvait bien 8 passages pertinents dans AZ-900-Master-Cheat-Sheet.pdf,
mais Qwen répondait directement "Information non trouvée dans les documents."
sans même tenter une affirmation. Cause : le prompt ne couvrait pas les
questions "méta" (quel document parle de X ?), amenant Qwen à chercher une
phrase qui dit littéralement "ce document parle de X" plutôt que de
reconnaître qu'un passage sur le sujet suffit. Corrigé dans SYSTEM_PROMPT.

Ces tests utilisent un VRAI RagEngine (donc sa VRAIE logique de validation),
mais avec un embedder/index factices (pas de FAISS/BGE-M3 réel — inutile ici,
on ne teste pas la pertinence de la recherche, déjà vérifiée manuellement
contre l'index réel) et `_generer_texte` simulé pour contrôler précisément ce
que "Qwen" répond à chaque scénario.
"""

import numpy as np
import pytest

from app.rag_engine import REPONSE_NON_TROUVEE, RagEngine


class FakeEmbedder:
    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.zeros((len(textes), 4), dtype="float32")


class FakeIndex:
    """Simule FAISS : renvoie les chunks dans l'ordre où ils ont été ajoutés,
    avec des scores décroissants plausibles. Suffisant pour tester la
    validation — la pertinence réelle de la recherche a déjà été vérifiée
    séparément contre l'index réel (voir le diagnostic de ce bug)."""

    def __init__(self, nb_chunks):
        self.nb_chunks = nb_chunks

    def search(self, embedding_question, k):
        k = min(k, self.nb_chunks)
        indices = np.arange(k).reshape(1, -1)
        scores = np.linspace(0.9, 0.5, k).reshape(1, -1).astype("float32")
        return scores, indices


def construire_engine(chunks: list[dict]) -> RagEngine:
    engine = RagEngine(index_dir="/non-utilise")
    engine.embedder = FakeEmbedder()
    engine.index = FakeIndex(len(chunks))
    engine.chunks = chunks
    engine.manifest = {"pdf": sorted({c["source"] for c in chunks})}
    engine.ready = True
    engine.tokenizer = object()  # jamais utilisé : _generer_texte est simulé ci-dessous
    engine.model = object()
    return engine


def simuler_generation(textes_bruts: list[str]):
    """Remplace RagEngine._generer_texte : renvoie successivement chaque texte
    de la liste (1er appel = génération principale, suivants = vérificateur),
    avec des comptages de tokens arbitraires (non testés ici)."""
    iterateur = iter(textes_bruts)

    def _mock(messages, max_new_tokens):
        return next(iterateur), 500, 50

    return _mock


def bloc_affirmation(affirmation: str, passage_id: str, page: int, citation: str) -> str:
    return f'AFFIRMATION: {affirmation}\nPASSAGE: {passage_id}\nPAGE: {page}\nCITATION: "{citation}"'


# --- Fixtures de contenu, inspirées des vrais documents indexés ---

CHUNK_AZURE = {
    "texte": (
        "Azure offers a wide range of resource types, including compute, storage, "
        "networking, and databases."
    ),
    "source": "AZ-900-Master-Cheat-Sheet.pdf",
    "page": 12,
}
CHUNK_VLLM = {
    "texte": "Le runtime LLM principal recommandé est vLLM, pour sa gestion efficace du batching.",
    "source": "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf",
    "page": 6,
}
CHUNK_ACCOMPAGNEMENT = {
    "texte": "Ce document décrit la procédure d'accompagnement des salariés en reconversion professionnelle.",
    "source": "Accompagnement2004.pdf",
    "page": 1,
}


class TestReponsesAcceptees:
    """Reproduit précisément le bug signalé, et deux cas voisins — vérifie
    qu'ils sont maintenant acceptés (plus de faux NOT_FOUND)."""

    def test_question_azure_est_acceptee(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure propose des types de ressources variés (calcul, stockage, réseau, bases de données).",
                        "P1",
                        12,
                        CHUNK_AZURE["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Quel document contient des informations relatives à Azure ?")

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert resultat["answer"] != REPONSE_NON_TROUVEE
        assert "AZ-900-Master-Cheat-Sheet.pdf" in resultat["answer"]
        assert len(resultat["validated_claims"]) == 1

    def test_document_vllm_est_accepte(self, monkeypatch):
        engine = construire_engine([CHUNK_VLLM])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Le runtime LLM principal recommandé est vLLM.",
                        "P1",
                        6,
                        CHUNK_VLLM["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Quel document parle de vLLM ?")

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf" in resultat["answer"]

    def test_resume_accompagnement_est_utile(self, monkeypatch):
        engine = construire_engine([CHUNK_ACCOMPAGNEMENT])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Le document décrit la procédure d'accompagnement des salariés en reconversion professionnelle.",
                        "P1",
                        1,
                        CHUNK_ACCOMPAGNEMENT["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Résume le sujet principal du document Accompagnement2004.pdf.")

        assert resultat["status"] != "NOT_FOUND"
        assert resultat["answer"] != REPONSE_NON_TROUVEE


class TestAbsenceReelleResteNotFound:
    """Le mécanisme anti-hallucination doit continuer à refuser une
    information réellement absente."""

    def test_directeur_financier_absent_donne_not_found(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE, CHUNK_VLLM, CHUNK_ACCOMPAGNEMENT])
        # Aucun passage ne contient cette information : Qwen répond
        # directement par la phrase, sans bloc AFFIRMATION (comportement voulu).
        monkeypatch.setattr(engine, "_generer_texte", simuler_generation([REPONSE_NON_TROUVEE]))

        resultat = engine.ask("Quel est le nom du directeur financier d'AFTECH ?")

        assert resultat["status"] == "NOT_FOUND"
        assert resultat["answer"] == REPONSE_NON_TROUVEE
        assert resultat["validated_claims"] == []


class TestRejetsDeSecurite:
    """Le mécanisme anti-hallucination doit continuer à rejeter les
    affirmations non prouvées — la correction du prompt ne doit rien affaiblir ici."""

    def test_citation_inventee_est_rejetee(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure a été lancé en février 2008.",
                        "P1",
                        12,
                        # Citation plausible mais FABRIQUÉE : absente du texte réel du passage.
                        "Azure a été lancé officiellement en février 2008 par Microsoft.",
                    ),
                    # Pas de second élément : le vérificateur ne doit JAMAIS être
                    # appelé ici (citation_presente échoue avant). S'il l'était,
                    # ce test échouerait avec StopIteration.
                ]
            ),
        )

        resultat = engine.ask("Quand Azure a-t-il été lancé ?")

        assert resultat["status"] == "NOT_FOUND"
        assert resultat["answer"] == REPONSE_NON_TROUVEE

    def test_citation_reelle_mais_mal_attribuee_est_rejetee(self, monkeypatch):
        # La citation existe mot pour mot dans le corpus, mais Qwen l'attribue
        # au mauvais passage (P2 = vLLM, alors que le texte vient d'ailleurs) :
        # notre vérité terrain (pas le LLM) doit détecter l'incohérence.
        engine = construire_engine([CHUNK_AZURE, CHUNK_VLLM])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure propose du stockage.",
                        "P2",  # passage vLLM, pas Azure
                        6,
                        CHUNK_AZURE["texte"],  # vraie citation, mais tirée du mauvais passage
                    ),
                ]
            ),
        )

        resultat = engine.ask("Que propose Azure comme stockage ?")

        assert resultat["status"] == "NOT_FOUND"
