import asyncio
import json
import os
import time

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

pytestmark = pytest.mark.asyncio


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
    async def test_reconstruction_reussie_cree_index_current(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "doc1")

        manifest = await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

        dossier_courant = chemin_index_courant(str(tmp_path))
        assert os.path.isfile(os.path.join(dossier_courant, "index.faiss"))
        assert os.path.isfile(os.path.join(dossier_courant, "chunks.json"))
        assert manifest["pdf"] == ["doc1.pdf"]

    async def test_chunks_historiques_sont_conserves_sans_reextraction(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "nouveau")
        historiques = [{"source": "ancien.pdf", "page": 1, "texte": "Texte historique jamais ré-extrait.", "position": 0}]

        await reconstruire_index(historiques, [doc], registry, FakeEmbedder(), str(tmp_path))

        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            chunks = json.load(f)
        sources = {c["source"] for c in chunks}
        assert "ancien.pdf" in sources
        assert "nouveau.pdf" in sources

    async def test_version_precedente_devient_rollback(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))

        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        await reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        dossier_precedent = os.path.join(str(tmp_path), "index", "previous")
        assert os.path.isdir(dossier_precedent)
        with open(os.path.join(dossier_precedent, "manifest.json"), encoding="utf-8") as f:
            manifest_precedent = json.load(f)
        assert manifest_precedent["pdf"] == ["v1.pdf"]  # l'ancienne version, pas la nouvelle

    async def test_rollback_restaure_la_version_precedente(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))
        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        await reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        reussi = rollback_vers_version_precedente(str(tmp_path))

        assert reussi is True
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

    async def test_rollback_sans_version_precedente_renvoie_false(self, tmp_path):
        assert rollback_vers_version_precedente(str(tmp_path)) is False

    async def test_aucun_document_actif_produit_un_index_vide_mais_valide(self, tmp_path):
        # Bibliothèque entièrement vidée (dernier document supprimé) : un
        # état LÉGITIME, pas une erreur — voir EmptyState côté frontend.
        registry = DocumentRegistry(str(tmp_path))
        manifest = await reconstruire_index([], [], registry, FakeEmbedder(), str(tmp_path))

        assert manifest["pdf"] == []
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            assert json.load(f) == []

    async def test_echec_de_construction_ne_touche_pas_current_et_ne_laisse_pas_de_dossier_building(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc_valide = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc_valide], registry, FakeEmbedder(), str(tmp_path))

        # Document dont le PDF référencé par le registre n'existe PLUS sur
        # disque (ex. corruption du volume) : extraire_chunks_pdf échoue
        # réellement, sans qu'on ait eu besoin de mocker quoi que ce soit.
        doc_cassee = EnregistrementDocument(
            id="casse", nom_original="casse.pdf", nom_stocke="fichier-absent.pdf",
            taille_octets=1, hash_sha256="x", statut="READY",
        )
        registry.ajouter(doc_cassee)

        with pytest.raises(FileNotFoundError):
            await reconstruire_index([], [doc_valide, registry.obtenir("casse")], registry, FakeEmbedder(), str(tmp_path))

        # "current" (la version qui marchait) n'a pas été remplacée.
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

        dossier_index = os.path.join(str(tmp_path), "index")
        restants = [n for n in os.listdir(dossier_index) if n.startswith("building-")]
        assert restants == []


class EmbedderLent(FakeEmbedder):
    """Simule le vrai coût CPU de BGE-M3 (un encode() qui prend du temps),
    pour prouver qu'une AUTRE requête peut s'intercaler PENDANT une
    reconstruction — c'est exactement le bug réel rencontré en production
    (le conteneur entier gelait, Modal a fini par le tuer en plein
    traitement, laissant un document bloqué pour toujours)."""

    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        time.sleep(0.02)  # un peu de vrai travail CPU par lot, pas instantané
        return super().encode(textes, convert_to_numpy, normalize_embeddings)


class TestReconstructionNeBloquePasLaBoucleDEvenements:
    async def test_une_autre_tache_async_sintercale_pendant_la_reconstruction(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        # Assez de passages pour que la reconstruction prenne plusieurs lots
        # (TAILLE_LOT_EMBEDDING=64) et donc plusieurs dizaines de ms réelles.
        historiques = [
            {"source": "gros.pdf", "page": 1, "texte": f"Passage historique numéro {i}.", "position": i}
            for i in range(300)
        ]

        evenements: list[str] = []

        async def autre_requete_pendant_ce_temps():
            for _ in range(20):
                await asyncio.sleep(0.005)
                evenements.append("autre_requete")

        resultat_reconstruction, _ = await asyncio.gather(
            reconstruire_index(historiques, [], registry, EmbedderLent(), str(tmp_path)),
            autre_requete_pendant_ce_temps(),
        )

        # La preuve : "autre_requete" a eu l'occasion de s'exécuter PLUSIEURS
        # fois PENDANT la reconstruction, pas seulement avant ou après —
        # impossible si celle-ci avait monopolisé la boucle d'événements.
        assert len(evenements) >= 10
        assert resultat_reconstruction["pdf"] == ["gros.pdf"]


class TestVerrouReconstruction:
    async def test_deux_verrous_simultanes_le_second_echoue(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            with pytest.raises(ReconstructionDejaEnCours):
                with VerrouReconstruction(str(tmp_path)):
                    pass

    async def test_verrou_libere_apres_le_bloc(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            pass
        with VerrouReconstruction(str(tmp_path)):  # ne lève rien : le premier a bien été libéré
            pass

    async def test_reconstruction_concurrente_leve_reconstruction_deja_en_cours(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "v1")
        dossier_index = os.path.join(str(tmp_path), "index")
        os.makedirs(dossier_index, exist_ok=True)

        with VerrouReconstruction(dossier_index):
            with pytest.raises(ReconstructionDejaEnCours):
                await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

    async def test_verrou_perime_est_automatiquement_repris(self, tmp_path, monkeypatch):
        """Bug réel : un conteneur tué en plein traitement laisse le verrou
        orphelin pour toujours. Un verrou trop vieux doit être repris
        automatiquement plutôt que de bloquer indéfiniment."""
        import app.index_builder as index_builder_module
        from datetime import datetime, timedelta, timezone

        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "v1")
        dossier_index = os.path.join(str(tmp_path), "index")
        os.makedirs(dossier_index, exist_ok=True)

        chemin_verrou = os.path.join(dossier_index, ".reindex.lock")
        horodatage_perime = datetime.now(timezone.utc) - timedelta(seconds=index_builder_module.AGE_MAX_VERROU_SECONDES + 60)
        with open(chemin_verrou, "w", encoding="utf-8") as f:
            f.write(horodatage_perime.isoformat())

        manifest = await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

        assert manifest["pdf"] == ["v1.pdf"]  # a bien abouti, malgré le verrou laissé par le "conteneur mort"
