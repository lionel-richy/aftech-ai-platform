"""Orchestration du cycle de vie d'un document déposé depuis la Bibliothèque :
UPLOADED -> EXTRACTING -> INDEXING -> READY (ou FAILED), et suppression
(-> DELETING -> reconstruction sans ce document).

Relie document_pipeline.py (validation, registre), index_builder.py
(reconstruction atomique) et rag_engine.py (recherche, rechargement à chaud).
Aucune dépendance à FastAPI/Modal ici — testable avec un RagEngine réel
(doubles de test) et un dossier temporaire, voir tests/test_document_manager.py.
"""

import logging
import os
from typing import Awaitable, Callable, Optional


async def _ne_rien_faire() -> None:
    pass

from . import index_builder
from .document_pipeline import (
    DocumentRegistry,
    EnregistrementDocument,
    FichierInvalide,
    TAILLE_MAX_OCTETS_DEFAUT,
    calculer_sha256,
    generer_id_document,
    nom_affichage_securise,
    valider_fichier_pdf,
)

logger = logging.getLogger("aftech.documents")


class DocumentDejaIndexe(Exception):
    """Un document avec le même contenu (SHA-256 identique) existe déjà."""

    def __init__(self, enregistrement_existant: dict):
        self.enregistrement_existant = enregistrement_existant
        super().__init__("Ce document (même contenu) est déjà indexé.")


class DocumentIntrouvable(Exception):
    pass


class DocumentManager:
    def __init__(
        self,
        racine_store: str,
        engine,
        taille_max_octets: int = TAILLE_MAX_OCTETS_DEFAUT,
        on_mutation: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.racine_store = racine_store
        self.engine = engine
        self.taille_max_octets = taille_max_octets
        self.registry = DocumentRegistry(racine_store)
        # Appelé (et TOUJOURS awaité) après chaque écriture durable — en
        # production, committe le Modal Volume (voir modal_app.py) pour que
        # les écritures survivent à un redémarrage de conteneur. Aucune
        # dépendance à `modal` ici : no-op en local/tests (voir main.py).
        self._on_mutation = on_mutation or _ne_rien_faire
        os.makedirs(os.path.join(racine_store, "documents"), exist_ok=True)

    # --- Dépôt ---

    async def deposer(self, contenu: bytes, nom_original: str) -> EnregistrementDocument:
        """Valide puis enregistre le fichier (statut UPLOADED) — ne lance PAS
        encore l'extraction/indexation (voir traiter(), appelé en tâche de
        fond par main.py : la requête d'upload répond vite). async pour
        pouvoir committer le Modal Volume sans bloquer (voir _on_mutation)."""
        valider_fichier_pdf(contenu, nom_original, self.taille_max_octets)  # lève FichierInvalide

        hash_sha256 = calculer_sha256(contenu)
        existant = self.registry.trouver_par_hash(hash_sha256)
        if existant is not None:
            raise DocumentDejaIndexe(existant)

        id_document = generer_id_document()
        enregistrement = EnregistrementDocument(
            id=id_document,
            nom_original=nom_affichage_securise(nom_original),
            nom_stocke=f"{id_document}.pdf",
            taille_octets=len(contenu),
            hash_sha256=hash_sha256,
            statut="UPLOADED",
        )

        # Nom de stockage dérivé UNIQUEMENT de l'id généré par le serveur —
        # jamais du nom fourni par l'utilisateur (exigence de sécurité).
        chemin_pdf = os.path.join(self.racine_store, "documents", enregistrement.nom_stocke)
        with open(chemin_pdf, "wb") as f:
            f.write(contenu)

        self.registry.ajouter(enregistrement)
        await self._on_mutation()
        logger.info("document ajouté id=%s taille=%d statut=UPLOADED", id_document, len(contenu))
        return enregistrement

    # --- Traitement (extraction + indexation), pensé pour tourner en tâche de fond ---
    #
    # ASYNC (pas juste par convention) : bug réel rencontré en production
    # (voir index_builder.py) — un traitement synchrone géant bloquait tout
    # le conteneur pendant plusieurs minutes, au point que Modal l'a
    # remplacé en pleine reconstruction, laissant un document bloqué pour
    # toujours en INDEXING. Starlette détecte qu'une BackgroundTask est une
    # coroutine et l'exécute nativement sur la boucle d'événements (voir
    # main.py) — c'est CE qui permet aux points de cession internes
    # (index_builder._encoder_par_lots) de garder le serveur réactif.

    async def traiter(self, id_document: str) -> None:
        self.registry.mettre_a_jour(id_document, statut="EXTRACTING")
        try:
            doc = self.registry.obtenir(id_document)
            if doc is None:
                raise DocumentIntrouvable(id_document)

            from pypdf import PdfReader

            chemin_pdf = self.registry.chemin_pdf(doc)
            nb_pages = len(PdfReader(chemin_pdf).pages)
            self.registry.mettre_a_jour(id_document, nb_pages=nb_pages, statut="INDEXING")

            await self._reconstruire_index_complet()

            self.registry.mettre_a_jour(id_document, statut="READY")
            await self._on_mutation()
            logger.info("document indexé id=%s statut=READY", id_document)
        except Exception as exc:  # noqa: BLE001 — jamais de traceback dans message_erreur
            logger.warning("échec indexation id=%s", id_document)
            self.registry.mettre_a_jour(id_document, statut="FAILED", message_erreur=str(exc)[:300])
            raise

    async def _reconstruire_index_complet(self) -> None:
        noms_geres = {d["nom_original"] for d in self.registry.lister()}
        chunks_historiques = self.engine.chunks_historiques(noms_geres)
        # INDEXING : le document qu'on vient de faire passer par cet état
        # (celui en cours de traitement) ; READY : les autres déjà indexés.
        documents_actifs = [d for d in self.registry.lister() if d["statut"] in ("INDEXING", "READY")]

        await index_builder.reconstruire_index(
            chunks_historiques, documents_actifs, self.registry, self.engine.embedder, self.racine_store
        )
        self.engine.recharger_index(index_builder.chemin_index_courant(self.racine_store))

    # --- Suppression ---

    async def supprimer(self, id_document: str) -> None:
        doc = self.registry.obtenir(id_document)
        if doc is None:
            raise DocumentIntrouvable(id_document)

        self.registry.mettre_a_jour(id_document, statut="DELETING")
        try:
            await self._reconstruire_index_complet_sans(id_document)
            chemin_pdf = self.registry.chemin_pdf(doc)
            if os.path.isfile(chemin_pdf):
                os.remove(chemin_pdf)
            self.registry.supprimer(id_document)
            await self._on_mutation()
            logger.info("document supprimé id=%s", id_document)
        except Exception:
            self.registry.mettre_a_jour(id_document, statut="FAILED", message_erreur="Échec de la suppression.")
            raise

    async def _reconstruire_index_complet_sans(self, id_exclu: str) -> None:
        noms_geres = {d["nom_original"] for d in self.registry.lister() if d["id"] != id_exclu}
        chunks_historiques = self.engine.chunks_historiques(noms_geres | {self.registry.obtenir(id_exclu)["nom_original"]})
        documents_actifs = [
            d for d in self.registry.lister() if d["id"] != id_exclu and d["statut"] in ("INDEXING", "READY")
        ]
        await index_builder.reconstruire_index(
            chunks_historiques, documents_actifs, self.registry, self.engine.embedder, self.racine_store
        )
        self.engine.recharger_index(index_builder.chemin_index_courant(self.racine_store))

    # --- Lecture ---

    def obtenir_statut(self, id_document: str) -> Optional[dict]:
        return self.registry.obtenir(id_document)

    def lister_tout(self) -> list[dict]:
        """Fusionne les documents HISTORIQUES (depuis engine.documents(), non
        supprimables) et ceux gérés par le registre (supprimables)."""
        geres = {d["nom_original"] for d in self.registry.lister()}
        historiques = [
            {**d, "supprimable": False} for d in self.engine.documents() if d["nom_fichier"] not in geres
        ]
        geres_formates = [
            {
                "nom_fichier": d["nom_original"],
                "pages": d["nb_pages"],
                "passages": d["nb_passages"],
                "hash_sha256": d["hash_sha256"],
                "modele_embeddings": "BAAI/bge-m3",
                "date_index": d["date_ajout"],
                "id": d["id"],
                "statut": d["statut"],
                "message_erreur": d.get("message_erreur"),
                "taille_octets": d["taille_octets"],
                "supprimable": True,
            }
            for d in self.registry.lister()
        ]
        return historiques + geres_formates
