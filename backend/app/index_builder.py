"""Reconstruction atomique de l'index FAISS, à partir :
- des chunks "historiques" (documents déjà indexés avant cette fonctionnalité,
  dont on n'a jamais eu le PDF d'origine sur ce volume — seul leur texte déjà
  extrait est conservé, jamais ré-extrait) ;
- des PDF réellement stockés sur le volume de documents (document_pipeline.py),
  ré-extraits à chaque reconstruction.

Jamais de remplacement direct : on construit une version temporaire, on la
valide, puis on bascule atomiquement (os.replace, atomique sur un même
système de fichiers POSIX — donc sur le même volume Modal). L'ancienne
version devient "previous" (rollback possible), jamais supprimée tout de
suite.

N'importe JAMAIS torch/transformers/Qwen : utilise seulement un embedder déjà
chargé (BGE-M3 sur CPU), passé en paramètre — voir app/rag_engine.py.
"""

import asyncio
import errno
import json
import os
import shutil
from datetime import datetime, timezone

TAILLE_PASSAGE = 800
CHEVAUCHEMENT = 150
# Bug réel rencontré en production : embedder.encode() sur TOUS les passages
# d'un coup (ex. 1489) bloque le GIL assez longtemps pour geler tout le
# conteneur (plus aucune requête servie) — Modal a fini par le remplacer,
# tuant la tâche en plein milieu (document resté bloqué en INDEXING,
# verrou de reconstruction jamais libéré). Encoder par petits lots, avec un
# point de cession explicite à la boucle d'événements entre chaque lot,
# laisse le serveur répondre aux autres requêtes pendant ce temps.
TAILLE_LOT_EMBEDDING = 64

NOM_LOCK = ".reindex.lock"
DOSSIER_COURANT = "current"
DOSSIER_PRECEDENT = "previous"
DIMENSION_BGE_M3 = 1024  # utilisée SEULEMENT si chunks est vide (voir plus bas) :
# on évite d'appeler embedder.encode([]) dont le comportement réel (modèle
# sentence_transformers) n'a pas été vérifié pour une liste vide.


class ReconstructionDejaEnCours(Exception):
    pass


class IndexInvalide(Exception):
    """Levée si la version temporaire construite ne passe pas la validation
    — dans ce cas, "current" n'est JAMAIS touché (voir reconstruire_index)."""


def decouper_texte(texte: str, taille: int = TAILLE_PASSAGE, chevauchement: int = CHEVAUCHEMENT) -> list[str]:
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def extraire_chunks_pdf(chemin_pdf: str, nom_source_affiche: str) -> list[dict]:
    """nom_source_affiche : nom ORIGINAL (pas le nom de stockage interne) —
    c'est ce que l'utilisateur et les citations doivent voir."""
    from pypdf import PdfReader

    chunks = []
    lecteur = PdfReader(chemin_pdf)
    position = 0
    for indice_page, page in enumerate(lecteur.pages):
        texte_page = page.extract_text() or ""
        for morceau in decouper_texte(texte_page):
            chunks.append(
                {"source": nom_source_affiche, "page": indice_page + 1, "texte": morceau, "position": position}
            )
            position += 1
    return chunks


AGE_MAX_VERROU_SECONDES = 15 * 60  # voir _verrou_est_perime ci-dessous


def _verrou_est_perime(chemin: str) -> bool:
    """Un conteneur tué/recyclé en plein traitement (ex. incident réel
    rencontré en production avant le passage à l'encodage par lots) laisse
    le verrou orphelin pour toujours, bloquant TOUTE future reconstruction.
    Un verrou plus vieux que AGE_MAX_VERROU_SECONDES est considéré abandonné
    et peut être repris — largement au-dessus du temps désormais nécessaire
    pour une reconstruction normale."""
    try:
        with open(chemin, encoding="utf-8") as f:
            horodatage = datetime.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return True  # illisible/corrompu : on ne le laisse pas bloquer indéfiniment
    age = datetime.now(timezone.utc) - horodatage
    return age.total_seconds() > AGE_MAX_VERROU_SECONDES


class VerrouReconstruction:
    """Verrou par fichier (O_CREAT|O_EXCL, atomique au niveau du système de
    fichiers) : empêche deux reconstructions simultanées, y compris entre
    process/conteneurs différents partageant le même volume."""

    def __init__(self, racine: str) -> None:
        self.chemin = os.path.join(racine, NOM_LOCK)

    def __enter__(self) -> "VerrouReconstruction":
        try:
            fd = os.open(self.chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(datetime.now(timezone.utc).isoformat()).encode("utf-8"))
            os.close(fd)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                if _verrou_est_perime(self.chemin):
                    os.remove(self.chemin)
                    return self.__enter__()  # une seule reprise : repart avec un verrou frais
                raise ReconstructionDejaEnCours(
                    "Une reconstruction d'index est déjà en cours — réessayez dans un instant."
                ) from exc
            raise
        return self

    def __exit__(self, *_exc) -> None:
        try:
            os.remove(self.chemin)
        except FileNotFoundError:
            pass


def _valider_dossier_index(dossier: str) -> None:
    """Charge réellement les 3 fichiers (pas seulement leur présence) :
    c'est la seule façon de détecter un index tronqué ou corrompu avant de
    le rendre actif."""
    import faiss

    for nom in ("index.faiss", "chunks.json", "manifest.json"):
        chemin = os.path.join(dossier, nom)
        if not os.path.isfile(chemin):
            raise IndexInvalide(f"Fichier manquant après construction : {nom}")

    try:
        index = faiss.read_index(os.path.join(dossier, "index.faiss"))
        with open(os.path.join(dossier, "chunks.json"), encoding="utf-8") as f:
            chunks = json.load(f)
        with open(os.path.join(dossier, "manifest.json"), encoding="utf-8") as f:
            json.load(f)
    except Exception as exc:  # noqa: BLE001 — n'importe quelle corruption doit être rejetée
        raise IndexInvalide(f"Index reconstruit invalide : {exc}") from exc

    if index.ntotal != len(chunks):
        raise IndexInvalide(
            f"Incohérence : {index.ntotal} vecteurs FAISS pour {len(chunks)} passages déclarés."
        )


async def _encoder_par_lots(embedder, textes: list[str]):
    """Encode en plusieurs appels COURTS (TAILLE_LOT_EMBEDDING passages à la
    fois), chacun délégué à un thread (asyncio.to_thread) avec un point de
    cession explicite entre deux lots — jamais un seul encode() géant qui
    accapare le GIL pendant plusieurs minutes d'affilée (voir le
    commentaire sur TAILLE_LOT_EMBEDDING)."""
    import numpy as np

    morceaux = []
    for debut in range(0, len(textes), TAILLE_LOT_EMBEDDING):
        lot = textes[debut : debut + TAILLE_LOT_EMBEDDING]
        embeddings_lot = await asyncio.to_thread(
            embedder.encode, lot, convert_to_numpy=True, normalize_embeddings=True
        )
        morceaux.append(embeddings_lot)
        await asyncio.sleep(0)  # cède explicitement la main à la boucle d'événements
    return np.concatenate(morceaux, axis=0)


async def reconstruire_index(
    chunks_historiques: list[dict],
    documents_actifs: list[dict],
    registry,
    embedder,
    racine_store: str,
) -> dict:
    """documents_actifs : enregistrements du registre (statut != DELETING/FAILED)
    à ré-extraire depuis leur PDF stocké. Renvoie le nouveau manifest.

    Protégée par VerrouReconstruction : lève ReconstructionDejaEnCours si un
    autre appel est déjà en cours (voir main.py, qui traduit ça en 409).

    ASYNC (pas juste par convention) : voir _encoder_par_lots — c'est ce qui
    permet au serveur de continuer à répondre à d'autres requêtes PENDANT
    une reconstruction, au lieu de geler tout le conteneur."""
    dossier_index = os.path.join(racine_store, "index")
    os.makedirs(dossier_index, exist_ok=True)

    with VerrouReconstruction(dossier_index):
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        dossier_temp = os.path.join(dossier_index, f"building-{horodatage}")
        os.makedirs(dossier_temp, exist_ok=True)

        try:
            chunks = list(chunks_historiques)
            hashes_pdf: dict[str, str] = {}
            stats_par_pdf: dict[str, dict] = {}

            for doc in documents_actifs:
                chemin_pdf = registry.chemin_pdf(doc)
                # À son tour délégué à un thread : plusieurs gros PDF
                # pourraient sinon retarder la cession à la boucle
                # d'événements, même si c'est rarement le facteur dominant.
                nouveaux = await asyncio.to_thread(extraire_chunks_pdf, chemin_pdf, doc["nom_original"])
                chunks.extend(nouveaux)
                hashes_pdf[doc["nom_original"]] = doc["hash_sha256"]
                stats_par_pdf[doc["nom_original"]] = {
                    "pages": doc["nb_pages"],
                    "passages": len(nouveaux),
                }
                registry.mettre_a_jour(doc["id"], nb_passages=len(nouveaux))

            # chunks vide est un état LÉGITIME (ex. suppression du dernier
            # document géré, sans document historique) — produit un index
            # FAISS à 0 vecteur, pas une erreur. rag_engine.py sait gérer une
            # recherche sur un index vide (voir _rechercher_passages).
            import faiss

            if chunks:
                textes = [c["texte"] for c in chunks]
                embeddings = (await _encoder_par_lots(embedder, textes)).astype("float32")
                index = faiss.IndexFlatIP(embeddings.shape[1])
                index.add(embeddings)
            else:
                index = faiss.IndexFlatIP(DIMENSION_BGE_M3)

            faiss.write_index(index, os.path.join(dossier_temp, "index.faiss"))
            with open(os.path.join(dossier_temp, "chunks.json"), "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)

            manifest = {
                "date_creation": datetime.now(timezone.utc).isoformat(),
                "modele_embeddings": "BAAI/bge-m3",
                "pdf": sorted({c["source"] for c in chunks}),
                "hashes_pdf": hashes_pdf,
                "stats_par_pdf": stats_par_pdf,
            }
            with open(os.path.join(dossier_temp, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            _valider_dossier_index(dossier_temp)

            # Bascule atomique : l'ancienne version "current" devient
            # "previous" (rollback possible), jamais supprimée directement.
            dossier_courant = os.path.join(dossier_index, DOSSIER_COURANT)
            dossier_precedent = os.path.join(dossier_index, DOSSIER_PRECEDENT)
            if os.path.isdir(dossier_courant):
                if os.path.isdir(dossier_precedent):
                    shutil.rmtree(dossier_precedent)
                os.replace(dossier_courant, dossier_precedent)
            os.replace(dossier_temp, dossier_courant)

            return manifest
        except Exception:
            shutil.rmtree(dossier_temp, ignore_errors=True)
            raise


def rollback_vers_version_precedente(racine_store: str) -> bool:
    """Renvoie False si aucune version précédente n'existe (rien à faire)."""
    dossier_index = os.path.join(racine_store, "index")
    os.makedirs(dossier_index, exist_ok=True)
    dossier_courant = os.path.join(dossier_index, DOSSIER_COURANT)
    dossier_precedent = os.path.join(dossier_index, DOSSIER_PRECEDENT)

    with VerrouReconstruction(dossier_index):
        if not os.path.isdir(dossier_precedent):
            return False
        if os.path.isdir(dossier_courant):
            shutil.rmtree(dossier_courant)
        os.replace(dossier_precedent, dossier_courant)
        return True


def chemin_index_courant(racine_store: str) -> str:
    return os.path.join(racine_store, "index", DOSSIER_COURANT)
