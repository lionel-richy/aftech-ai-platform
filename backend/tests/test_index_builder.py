import json
import os

import numpy as np
import pytest
from pdf_helpers import pdf_valide

from app.document_pipeline import DocumentRegistry, EnregistrementDocument
from app.index_builder import (
    IndexInvalide,
    ReconstructionDejaEnCours,
    VerrouReconstruction,
    chemin_index_courant,
    reconstruire_index,
    rollback_vers_version_precedente,
)


class FakeEmbedder:
    """Pure numpy, comme dans test_rag_engine_validation.py : on ne teste
    pas la qualité des embeddings, seulement la mécanique de reconstruction."""

    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.random.RandomState(0).rand(len(textes), 4).astype("float32")


def _enregistrer_pdf(tmp_path, registry: DocumentRegistry, nom: str, statut="READY") -> dict:
    os.makedirs(os.path.join(str(tmp_path), "documents"), exist_ok=True)
    contenu = pdf_valide()
    nom_stocke = f"{nom}.pdf"
    with open(os.path.join(str(tmp_path), "documents", nom_stocke), "wb") as f:
        f.write(contenu)
    enregistrement = EnregistrementDocument(
        id=nom,
        nom_original=f"{nom}.pdf",
        nom_stocke=nom_stocke,
        taille_octets=len(contenu),
        hash_sha256=f"hash-{nom}",
        nb_pages=1,
        statut=statut,
    )
    registry.ajouter(enregistrement)
    return registry.obtenir(nom)


class TestReconstructionAtomique:
    def test_reconstruction_reussie_cree_index_current(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "doc1")

        manifest = reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

        dossier_courant = chemin_index_courant(str(tmp_path))
        assert os.path.isfile(os.path.join(dossier_courant, "index.faiss"))
        assert os.path.isfile(os.path.join(dossier_courant, "chunks.json"))
        assert manifest["pdf"] == ["doc1.pdf"]

    def test_chunks_historiques_sont_conserves_sans_reextraction(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "nouveau")
        historiques = [{"source": "ancien.pdf", "page": 1, "texte": "Texte historique jamais ré-extrait.", "position": 0}]

        reconstruire_index(historiques, [doc], registry, FakeEmbedder(), str(tmp_path))

        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            chunks = json.load(f)
        sources = {c["source"] for c in chunks}
        assert "ancien.pdf" in sources
        assert "nouveau.pdf" in sources

    def test_version_precedente_devient_rollback(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))

        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        dossier_precedent = os.path.join(str(tmp_path), "index", "previous")
        assert os.path.isdir(dossier_precedent)
        with open(os.path.join(dossier_precedent, "manifest.json"), encoding="utf-8") as f:
            manifest_precedent = json.load(f)
        assert manifest_precedent["pdf"] == ["v1.pdf"]  # l'ancienne version, pas la nouvelle

    def test_rollback_restaure_la_version_precedente(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))
        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        reussi = rollback_vers_version_precedente(str(tmp_path))

        assert reussi is True
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

    def test_rollback_sans_version_precedente_renvoie_false(self, tmp_path):
        assert rollback_vers_version_precedente(str(tmp_path)) is False

    def test_aucun_document_actif_produit_un_index_vide_mais_valide(self, tmp_path):
        # Bibliothèque entièrement vidée (dernier document supprimé) : un
        # état LÉGITIME, pas une erreur — voir EmptyState côté frontend.
        registry = DocumentRegistry(str(tmp_path))
        manifest = reconstruire_index([], [], registry, FakeEmbedder(), str(tmp_path))

        assert manifest["pdf"] == []
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            assert json.load(f) == []

    def test_echec_de_construction_ne_touche_pas_current_et_ne_laisse_pas_de_dossier_building(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc_valide = _enregistrer_pdf(tmp_path, registry, "v1")
        reconstruire_index([], [doc_valide], registry, FakeEmbedder(), str(tmp_path))

        # Document dont le PDF référencé par le registre n'existe PLUS sur
        # disque (ex. corruption du volume) : extraire_chunks_pdf échoue
        # réellement, sans qu'on ait eu besoin de mocker quoi que ce soit.
        doc_cassee = EnregistrementDocument(
            id="casse", nom_original="casse.pdf", nom_stocke="fichier-absent.pdf",
            taille_octets=1, hash_sha256="x", statut="READY",
        )
        registry.ajouter(doc_cassee)

        with pytest.raises(FileNotFoundError):
            reconstruire_index([], [doc_valide, registry.obtenir("casse")], registry, FakeEmbedder(), str(tmp_path))

        # "current" (la version qui marchait) n'a pas été remplacée.
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

        dossier_index = os.path.join(str(tmp_path), "index")
        restants = [n for n in os.listdir(dossier_index) if n.startswith("building-")]
        assert restants == []


class TestVerrouReconstruction:
    def test_deux_verrous_simultanes_le_second_echoue(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            with pytest.raises(ReconstructionDejaEnCours):
                with VerrouReconstruction(str(tmp_path)):
                    pass

    def test_verrou_libere_apres_le_bloc(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            pass
        with VerrouReconstruction(str(tmp_path)):  # ne lève rien : le premier a bien été libéré
            pass

    def test_reconstruction_concurrente_leve_reconstruction_deja_en_cours(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "v1")
        dossier_index = os.path.join(str(tmp_path), "index")
        os.makedirs(dossier_index, exist_ok=True)

        with VerrouReconstruction(dossier_index):
            with pytest.raises(ReconstructionDejaEnCours):
                reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))
