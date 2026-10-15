"""Validation, nommage sûr et registre des documents déposés par un
utilisateur depuis la Bibliothèque — tout ce qui précède l'indexation
elle-même (voir index_builder.py pour la reconstruction FAISS).

Pure Python, aucune dépendance à Modal ni FastAPI : testable avec un simple
répertoire temporaire (voir tests/test_document_pipeline.py), comme
rag_engine.py l'est déjà avec des doubles de test.
"""

import io
import json
import os
import re
import threading
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

StatutDocument = Literal["UPLOADED", "EXTRACTING", "INDEXING", "READY", "FAILED", "DELETING"]

TAILLE_MAX_OCTETS_DEFAUT = 25 * 1024 * 1024  # 25 Mo, configurable (voir main.py)
SIGNATURE_PDF = b"%PDF-"


class FichierInvalide(Exception):
    """Message TOUJOURS non sensible (jamais de chemin disque, jamais de
    contenu du fichier) : exposé tel quel au client comme message_erreur."""


def valider_fichier_pdf(contenu: bytes, nom_original: str, taille_max_octets: int = TAILLE_MAX_OCTETS_DEFAUT) -> None:
    """Vérifications RÉELLES (pas seulement l'extension) : taille, signature
    binaire PDF, structure lisible par pypdf, non chiffré, au moins une page.
    Lève FichierInvalide avec une raison précise si l'un de ces points échoue.
    """
    if not nom_original.lower().endswith(".pdf"):
        raise FichierInvalide("Seuls les fichiers .pdf sont acceptés.")

    if len(contenu) == 0:
        raise FichierInvalide("Le fichier est vide.")

    if len(contenu) > taille_max_octets:
        raise FichierInvalide(f"Fichier trop volumineux (max {taille_max_octets // (1024 * 1024)} Mo).")

    # Signature binaire réelle (le "type MIME" déclaré par le navigateur n'est
    # jamais fiable) : un vrai PDF commence par "%PDF-", où qu'il se trouve
    # dans les ~1024 premiers octets (certains outils ajoutent un préambule).
    if SIGNATURE_PDF not in contenu[:1024]:
        raise FichierInvalide("Le contenu du fichier n'est pas un PDF valide (signature absente).")

    try:
        lecteur = PdfReader(io.BytesIO(contenu))
    except PdfReadError as exc:
        raise FichierInvalide("Le fichier PDF est corrompu ou illisible.") from exc

    if lecteur.is_encrypted:
        raise FichierInvalide("Les fichiers PDF chiffrés ne sont pas acceptés.")

    if len(lecteur.pages) == 0:
        raise FichierInvalide("Le PDF ne contient aucune page.")


_CARACTERES_SURS = re.compile(r"[^A-Za-z0-9._ -]")


def nom_affichage_securise(nom_original: str) -> str:
    """Nettoie le nom ORIGINAL pour un affichage sûr (jamais utilisé comme
    chemin disque — voir generer_id_document pour le nom de stockage réel).
    Retire tout séparateur de chemin et les caractères de contrôle."""
    nom = unicodedata.normalize("NFKC", nom_original)
    nom = os.path.basename(nom)  # retire tout "../" ou "/..." fourni par le client
    nom = _CARACTERES_SURS.sub("_", nom)
    nom = nom.strip(" ._") or "document.pdf"
    return nom[:200]


def generer_id_document() -> str:
    return uuid.uuid4().hex


def calculer_sha256(contenu: bytes) -> str:
    import hashlib

    return hashlib.sha256(contenu).hexdigest()


@dataclass
class EnregistrementDocument:
    id: str
    nom_original: str
    nom_stocke: str  # "<id>.pdf" — jamais dérivé du nom fourni par l'utilisateur
    taille_octets: int
    hash_sha256: str
    nb_pages: int = 0
    nb_passages: int = 0
    date_ajout: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    statut: StatutDocument = "UPLOADED"
    message_erreur: Optional[str] = None


class DocumentRegistry:
    """Persiste la liste des documents gérés (registry.json) dans le dossier
    racine du store (volume Modal en production, dossier local en test).
    Un verrou mémoire protège contre les écritures concurrentes DANS CE
    PROCESS ; sur Modal, le volume doit être committé après chaque écriture
    (voir modal_app.py) pour que les autres conteneurs voient les changements."""

    def __init__(self, racine: str) -> None:
        self.racine = racine
        self.chemin_registry = os.path.join(racine, "registry.json")
        self._verrou = threading.Lock()
        os.makedirs(racine, exist_ok=True)

    def _lire(self) -> dict[str, dict]:
        if not os.path.isfile(self.chemin_registry):
            return {}
        with open(self.chemin_registry, encoding="utf-8") as f:
            return json.load(f)

    def _ecrire(self, donnees: dict[str, dict]) -> None:
        chemin_tmp = self.chemin_registry + ".tmp"
        with open(chemin_tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(chemin_tmp, self.chemin_registry)  # écriture atomique

    def ajouter(self, enregistrement: EnregistrementDocument) -> None:
        with self._verrou:
            donnees = self._lire()
            donnees[enregistrement.id] = asdict(enregistrement)
            self._ecrire(donnees)

    def mettre_a_jour(self, id_document: str, **champs) -> None:
        with self._verrou:
            donnees = self._lire()
            if id_document not in donnees:
                raise KeyError(f"Document {id_document!r} introuvable dans le registre.")
            donnees[id_document].update(champs)
            self._ecrire(donnees)

    def supprimer(self, id_document: str) -> None:
        with self._verrou:
            donnees = self._lire()
            donnees.pop(id_document, None)
            self._ecrire(donnees)

    def obtenir(self, id_document: str) -> Optional[dict]:
        return self._lire().get(id_document)

    def lister(self) -> list[dict]:
        return list(self._lire().values())

    def trouver_par_hash(self, hash_sha256: str) -> Optional[dict]:
        for doc in self._lire().values():
            if doc["hash_sha256"] == hash_sha256 and doc["statut"] != "DELETING":
                return doc
        return None

    def chemin_pdf(self, enregistrement_ou_id) -> str:
        nom_stocke = (
            enregistrement_ou_id["nom_stocke"]
            if isinstance(enregistrement_ou_id, dict)
            else self.obtenir(enregistrement_ou_id)["nom_stocke"]
        )
        return os.path.join(self.racine, "documents", nom_stocke)
