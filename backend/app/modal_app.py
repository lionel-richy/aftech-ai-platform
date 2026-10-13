"""Déploiement Modal du backend FastAPI (GPU attaché).

Ce fichier ne lance RIEN tout seul : il déclare la configuration. Le
déploiement réel se fait via backend/scripts/modal_deploy.sh (volontairement
PAS automatique — voir docs/MODAL_COST_SAFETY.md).

À exécuter depuis le dossier backend/ (pour que "app" soit un module Python
importable au premier niveau) :
    cd backend && modal deploy app/modal_app.py

Choix du GPU — basé sur le benchmark réel (results/benchmarks/gpu/) :
  T4   : 7.6 tokens/s,  22.48 s/réponse, pic 4.64 Go
  L4   : 12.4 tokens/s, 15.33 s/réponse, pic 3.02 Go
  A100 : 13.2 tokens/s, 15.06 s/réponse, pic 3.02 Go
L4 est quasiment aussi rapide que A100 pour Qwen 4B, mais nettement moins
coûteux : c'est le GPU recommandé pour la démonstration. T4 reste le profil
économique. A100 N'APPORTE RIEN pour ce modèle et est explicitement interdit
ci-dessous (MODAL_GPU_TYPE ne peut valoir que "T4" ou "L4").

Paramètres de coût/sécurité choisis :
- GPU L4 par défaut ; MODAL_GPU_TYPE="T4" pour le profil économique.
  Toute autre valeur (y compris "A100") fait échouer le déploiement
  immédiatement, avec un message clair, plutôt que de l'autoriser.
- min_containers=0 : aucun conteneur ne tourne (donc aucun coût) tant que
  personne n'appelle l'API.
- max_containers=1 : un seul conteneur GPU à la fois (pas d'emballement de
  coût si plusieurs requêtes arrivent en même temps).
- scaledown_window=300 : le conteneur s'arrête 5 minutes après la dernière
  requête (pas immédiatement, pour éviter de recharger le modèle à chaque
  appel ; pas indéfiniment non plus).
- Aucun service permanent : pas de @app.function supplémentaire qui tournerait
  en continu, un seul point d'entrée (web), lui-même scale-to-zero.

Ces chiffres (signature exacte des paramètres Modal) ont été vérifiés contre
le paquet `modal` réellement installé (version 1.6.1), pas supposés depuis
la documentation en ligne.
"""

import os

import modal

from app.gpu_config import resoudre_gpu_type

GPU_TYPE = resoudre_gpu_type()
SCALEDOWN_WINDOW_SECONDES = 300
MAX_CONTAINERS = 1
MIN_CONTAINERS = 0

app = modal.App("aftech-ai-platform")

# Cache Hugging Face (poids de Qwen + BGE-M3) : persistant entre redémarrages
# de conteneur, pour ne pas re-télécharger plusieurs Go à chaque cold start.
hf_cache_volume = modal.Volume.from_name("aftech-hf-cache", create_if_missing=True)

# Secret Modal contenant BACKEND_API_KEY (et toute autre valeur sensible).
# Créé une seule fois, en dehors du code, via :
#   modal secret create aftech-backend-secrets BACKEND_API_KEY=<valeur>
# required_keys : Modal refuse le déploiement si le secret existe mais ne
# contient pas BACKEND_API_KEY — c'est la SEULE source autorisée pour cette
# clé (jamais codée en dur, jamais une autre variable d'environnement).
backend_secret = modal.Secret.from_name("aftech-backend-secrets", required_keys=["BACKEND_API_KEY"])

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    # Index déjà construit (scripts/build_document_index.py) : embarqué dans
    # l'image, pas recalculé sur Modal.
    .add_local_dir(
        "../data/indexes/aftech_documents",
        remote_path="/app/data/indexes/aftech_documents",
    )
    # Code de l'application (le paquet "app" lui-même).
    .add_local_python_source("app")
)


@app.function(
    image=image,
    gpu=GPU_TYPE,
    volumes={"/root/.cache/huggingface": hf_cache_volume},
    secrets=[backend_secret],
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW_SECONDES,
)
@modal.asgi_app()
def web():
    # Métrique de démarrage (sans contenu sensible) : visible dans `modal app logs`.
    print(f"[modal] démarrage d'un conteneur — GPU={GPU_TYPE}, index=/app/data/indexes/aftech_documents")

    os.environ.setdefault("INDEX_DIR", "/app/data/indexes/aftech_documents")

    from app.main import app as fastapi_app

    return fastapi_app
