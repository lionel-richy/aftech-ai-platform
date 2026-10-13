"""Tests du contrat trilingue (response_language) du RagEngine.

Exigences couvertes ici :
- le backend répond dans response_language MÊME quand le document source est
  dans une autre langue (question française sur document anglais ; question
  allemande sur document anglais) ;
- la citation exacte (validated_claims[].citation) et le nom de fichier
  restent TOUJOURS dans leur langue d'origine, jamais traduits ;
- une langue non supportée est refusée par le moteur.

Mêmes doubles de test que test_rag_engine_validation.py (FakeEmbedder/
FakeIndex en pur numpy, _generer_texte simulé) : on ne re-teste pas la
pertinence de la recherche, déjà couverte ailleurs.
"""

import pytest

from app.rag_engine import REPONSE_NON_TROUVEE_PAR_LANGUE
from test_rag_engine_validation import (
    CHUNK_AZURE,
    bloc_affirmation,
    construire_engine,
    simuler_generation,
)


class TestReponseDansLaLangueDemandee:
    def test_question_francaise_sur_document_anglais(self, monkeypatch):
        # CHUNK_AZURE est un passage en ANGLAIS. La question est en français
        # et response_language="fr" (défaut) : l'affirmation générée doit
        # être en français, mais la CITATION reste le texte anglais exact.
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

        resultat = engine.ask(
            "Quel document contient des informations relatives à Azure ?",
            response_language="fr",
        )

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Azure propose des types de ressources variés" in resultat["answer"]
        assert "[source :" in resultat["answer"]
        claim = resultat["validated_claims"][0]
        # La citation reste la phrase ANGLAISE d'origine, verbatim.
        assert claim["citation"] == CHUNK_AZURE["texte"]

    def test_question_allemande_sur_document_anglais(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure bietet eine Vielzahl von Ressourcentypen (Compute, Speicher, Netzwerk, Datenbanken) an.",
                        "P1",
                        12,
                        CHUNK_AZURE["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask(
            "Welches Dokument enthält Informationen zu Azure?",
            response_language="de",
        )

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Azure bietet eine Vielzahl" in resultat["answer"]
        # Suffixe de source en allemand ("Quelle"/"Seite"), jamais traduit en
        # français ou anglais.
        assert "[Quelle:" in resultat["answer"]
        assert "Seite 12" in resultat["answer"]
        claim = resultat["validated_claims"][0]
        # La citation reste la phrase ANGLAISE d'origine, verbatim — jamais
        # traduite en allemand.
        assert claim["citation"] == CHUNK_AZURE["texte"]

    def test_not_found_est_dans_la_langue_demandee(self, monkeypatch):
        for langue, phrase_attendue in REPONSE_NON_TROUVEE_PAR_LANGUE.items():
            engine = construire_engine([CHUNK_AZURE])
            monkeypatch.setattr(engine, "_generer_texte", simuler_generation([phrase_attendue]))

            resultat = engine.ask("Quel est le nom du directeur financier d'AFTECH ?", response_language=langue)

            assert resultat["status"] == "NOT_FOUND"
            assert resultat["answer"] == phrase_attendue


class TestLangueInvalide:
    def test_langue_non_supportee_leve_value_error(self):
        engine = construire_engine([CHUNK_AZURE])
        with pytest.raises(ValueError):
            engine.ask("Quand Azure a-t-il été lancé ?", response_language="es")
