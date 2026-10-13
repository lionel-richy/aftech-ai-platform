"""
Construction (ou réutilisation) d'un index FAISS multi-PDF pour AFTECH.

Contrairement à pdf_assistant.py (qui relit et ré-embeddingue un seul PDF à
chaque exécution), ce script construit un index RÉUTILISABLE pour plusieurs
PDF à la fois :
- index.faiss   : les embeddings de tous les passages, prêts pour la recherche
- chunks.json   : le texte de chaque passage + sa provenance (fichier, page)
- manifest.json : les métadonnées (date, modèle, hash des PDF...) qui
                  permettent de savoir si l'index est encore à jour.

Si aucun PDF n'a changé depuis la dernière construction, on ne recalcule
rien : les embeddings sont l'étape la plus lente, donc les réutiliser est
le principal intérêt de cet index.
"""

import argparse
import glob
import hashlib
import json
import os
from datetime import datetime, timezone

import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

TAILLE_PASSAGE = 800  # nombre de caractères par passage (environ)
CHEVAUCHEMENT = 150  # caractères communs entre deux passages consécutifs

DOSSIER_PDF_DEFAUT = "data/documents"
DOSSIER_INDEX_DEFAUT = "data/indexes/aftech_documents"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Construit ou réutilise un index FAISS à partir d'un dossier de PDF."
    )
    # Options nommées (pas de positionnel) : "colab exec" exécute ce code dans
    # un kernel Jupyter déjà lancé, dont les propres arguments (ex. "-f
    # <fichier-de-connexion>") sont visibles ici. Un positionnel optionnel
    # capturerait ce chemin par erreur ; une option nommée ne peut être
    # remplie que par "--dossier-pdf ...", ce qui n'arrivera jamais depuis le kernel.
    parser.add_argument(
        "--dossier-pdf",
        dest="dossier_pdf",
        default=DOSSIER_PDF_DEFAUT,
        help=f"Dossier contenant les PDF à indexer (défaut : {DOSSIER_PDF_DEFAUT})",
    )
    parser.add_argument(
        "--index-dir",
        default=DOSSIER_INDEX_DEFAUT,
        help=f"Dossier où enregistrer/lire l'index (défaut : {DOSSIER_INDEX_DEFAUT})",
    )
    # parse_known_args (et non parse_args), pour la même raison : les autres
    # arguments du kernel (ex. "-f") sont ignorés silencieusement.
    args, _ = parser.parse_known_args()
    return args


def decouper_texte(texte, taille=TAILLE_PASSAGE, chevauchement=CHEVAUCHEMENT):
    """Découpe un long texte en passages de taille fixe, avec chevauchement
    (évite qu'une phrase importante soit coupée en deux à la frontière)."""
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def calculer_hash_fichier(chemin):
    """Empreinte SHA-256 d'un fichier : sert à détecter si un PDF a changé,
    sans avoir à comparer tout son contenu texte par texte."""
    sha256 = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(8192), b""):
            sha256.update(bloc)
    return sha256.hexdigest()


def charger_manifest_existant(index_dir):
    chemin_manifest = os.path.join(index_dir, "manifest.json")
    if not os.path.isfile(chemin_manifest):
        return None
    with open(chemin_manifest, encoding="utf-8") as f:
        return json.load(f)


def determiner_si_reconstruction_necessaire(manifest_existant, hash_actuels, index_dir):
    """Compare les PDF actuels à ceux du dernier index construit.

    Renvoie (reconstruction_necessaire, raison_lisible).
    """
    fichiers_index = ["index.faiss", "chunks.json", "manifest.json"]
    if any(not os.path.isfile(os.path.join(index_dir, f)) for f in fichiers_index):
        return True, "aucun index existant (ou incomplet)"

    if manifest_existant is None:
        return True, "aucun index existant"

    hash_precedents = manifest_existant.get("hashes_pdf", {})
    fichiers_actuels = set(hash_actuels)
    fichiers_precedents = set(hash_precedents)

    ajoutes = fichiers_actuels - fichiers_precedents
    supprimes = fichiers_precedents - fichiers_actuels
    modifies = {
        f for f in (fichiers_actuels & fichiers_precedents) if hash_actuels[f] != hash_precedents[f]
    }

    if ajoutes:
        return True, f"nouveau(x) fichier(s) détecté(s) : {sorted(ajoutes)}"
    if supprimes:
        return True, f"fichier(s) supprimé(s) : {sorted(supprimes)}"
    if modifies:
        return True, f"fichier(s) modifié(s) : {sorted(modifies)}"
    return False, None


def extraire_chunks(fichiers_pdf):
    """Lit chaque PDF page par page et le découpe en passages ("chunks").

    Chaque chunk garde : un identifiant unique, le fichier source, le numéro
    de page réel (à partir de 1), le texte, et sa position dans SON document
    (utile pour retrouver plus tard le passage précédent/suivant).
    """
    chunks = []
    stats_par_pdf = {}

    for chemin_pdf in fichiers_pdf:
        nom_fichier = os.path.basename(chemin_pdf)
        prefixe_id = os.path.splitext(nom_fichier)[0]
        lecteur = PdfReader(chemin_pdf)

        position = 0
        for indice_page, page in enumerate(lecteur.pages):
            numero_page = indice_page + 1  # les pages humaines commencent à 1
            texte_page = page.extract_text() or ""

            for morceau in decouper_texte(texte_page):
                chunks.append(
                    {
                        "id": f"{prefixe_id}-{position:04d}",
                        "source": nom_fichier,
                        "page": numero_page,
                        "texte": morceau,
                        "position": position,
                    }
                )
                position += 1

        stats_par_pdf[nom_fichier] = {"pages": len(lecteur.pages), "passages": position}

    return chunks, stats_par_pdf


def construire_index(fichiers_pdf, hash_actuels, index_dir):
    print(f"Extraction du texte de {len(fichiers_pdf)} PDF...")
    chunks, stats_par_pdf = extraire_chunks(fichiers_pdf)
    print(f"{len(chunks)} passages extraits au total.")
    for nom, stats in stats_par_pdf.items():
        print(f"  - {nom} : {stats['pages']} pages, {stats['passages']} passages")

    print(f"\nChargement du modèle d'embeddings {EMBEDDING_MODEL_NAME} sur CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Calcul des embeddings de tous les passages (étape la plus longue)...")
    textes = [chunk["texte"] for chunk in chunks]
    embeddings = embedder.encode(
        textes,
        convert_to_numpy=True,
        normalize_embeddings=True,  # normalisé -> produit scalaire = similarité cosinus
        show_progress_bar=True,
    ).astype("float32")

    print("Construction de l'index FAISS...")
    index = faiss.IndexFlatIP(embeddings.shape[1])  # IP = produit scalaire (cosinus, car normalisé)
    index.add(embeddings)

    os.makedirs(index_dir, exist_ok=True)

    faiss.write_index(index, os.path.join(index_dir, "index.faiss"))

    with open(os.path.join(index_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    manifest = {
        "date_creation": datetime.now(timezone.utc).isoformat(),
        "modele_embeddings": EMBEDDING_MODEL_NAME,
        "pdf": sorted(hash_actuels),
        "hashes_pdf": hash_actuels,
        "stats_par_pdf": stats_par_pdf,
    }
    with open(os.path.join(index_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nIndex construit et enregistré dans {index_dir}/")


def main():
    args = parse_args()

    fichiers_pdf = sorted(glob.glob(os.path.join(args.dossier_pdf, "*.pdf")))
    if not fichiers_pdf:
        raise SystemExit(f"Aucun PDF trouvé dans {args.dossier_pdf}")

    print(f"{len(fichiers_pdf)} PDF trouvés dans {args.dossier_pdf} :")
    for chemin in fichiers_pdf:
        print(f"  - {os.path.basename(chemin)}")

    print("\nCalcul des empreintes SHA-256 (pour détecter un changement de PDF)...")
    hash_actuels = {os.path.basename(p): calculer_hash_fichier(p) for p in fichiers_pdf}

    manifest_existant = charger_manifest_existant(args.index_dir)
    reconstruction, raison = determiner_si_reconstruction_necessaire(
        manifest_existant, hash_actuels, args.index_dir
    )

    if not reconstruction:
        print("Index existant réutilisé.")
        return

    print(f"Reconstruction de l'index : {raison}")
    construire_index(fichiers_pdf, hash_actuels, args.index_dir)


if __name__ == "__main__":
    main()
