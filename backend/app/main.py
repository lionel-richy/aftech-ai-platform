"""API FastAPI de la plateforme AFTECH AI.

Différences connues avec l'API OpenAI officielle (/v1/chat/completions) :
- seul le DERNIER message "user" est utilisé (pas d'historique multi-tour
  côté serveur : la mémoire de conversation, si besoin, reste côté client
  pour cette Demo V1 — voir docs/KNOWN_LIMITATIONS.md) ;
- `usage` (prompt_tokens/completion_tokens/total_tokens) est toujours à 0 :
  nous n'avons pas encore instrumenté le comptage de tokens réel ;
  mieux vaut l'afficher à 0 que d'inventer un chiffre ;
- `temperature` est accepté mais actuellement ignoré (génération déterministe
  `do_sample=False`, pour la reproductibilité des réponses validées) ;
- pas de streaming (pas de `stream: true`) dans cette version.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import schemas
from .document_manager import DocumentDejaIndexe, DocumentIntrouvable, DocumentManager
from .document_pipeline import FichierInvalide
from .index_builder import ReconstructionDejaEnCours
from .metrics import metrics_store
from .rag_engine import BackendUnavailable, RagEngine
from .security import get_cors_origins, verify_api_key

API_VERSION = "0.1.0"
LIMITE_QUESTION_CARACTERES = 2000
DOCUMENT_STORE_DIR = os.environ.get("DOCUMENT_STORE_DIR", "data/document_store")
TAILLE_MAX_UPLOAD_OCTETS = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def _callback_commit_volume_si_modal():
    """None en local/tests (pas de `modal` requis). Sur Modal, modal_app.py
    définit DOCUMENT_STORE_VOLUME_NAME : on committe le Volume après chaque
    écriture durable pour qu'elle survive à un redémarrage de conteneur —
    import de `modal` PARESSEUX (jamais au niveau module), comme pour
    torch/faiss dans rag_engine.py."""
    nom_volume = os.environ.get("DOCUMENT_STORE_VOLUME_NAME")
    if not nom_volume:
        return None

    async def _commit() -> None:
        import modal

        # .commit.aio() (pas .commit()) : l'équivalent async natif de Modal,
        # pour ne jamais bloquer la boucle d'événements sur cet appel réseau
        # (voir AsyncUsageWarning observée en production avec .commit()).
        await modal.Volume.from_name(nom_volume).commit.aio()

    return _commit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chargement UNE SEULE FOIS par conteneur/process, avant de servir la
    # moindre requête (donc /health ne déclenche jamais ce chargement).
    engine = RagEngine()
    engine.load()
    app.state.engine = engine
    # Dégradé proprement si l'engine n'a pas pu charger l'embedder (ex. pas
    # d'index du tout en local) : DocumentManager a juste besoin de
    # engine.embedder, pas de Qwen — voir document_manager.py.
    app.state.document_manager = DocumentManager(
        DOCUMENT_STORE_DIR, engine, TAILLE_MAX_UPLOAD_OCTETS, on_mutation=_callback_commit_volume_si_modal()
    )
    yield


app = FastAPI(title="AFTECH AI Platform API", version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_engine(request: Request) -> RagEngine:
    return request.app.state.engine


def get_document_manager(request: Request) -> DocumentManager:
    return request.app.state.document_manager


def _repondre_ou_erreur(
    engine: RagEngine, question: str, top_k: int, response_language: str = "fr"
) -> tuple[dict, str]:
    """Factorise la gestion d'erreur commune à /ask et /v1/chat/completions :
    jamais de traceback renvoyé au client, toujours un request_id pour le
    diagnostic côté logs serveur."""
    request_id = str(uuid.uuid4())
    debut = time.perf_counter()
    try:
        resultat = engine.ask(question, top_k, response_language=response_language)
    except BackendUnavailable as exc:
        metrics_store.record_error()
        raise HTTPException(status_code=503, detail=f"Backend indisponible : {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — volontaire : jamais de 500 opaque avec traceback
        metrics_store.record_error()
        raise HTTPException(
            status_code=500, detail=f"Erreur interne (request_id={request_id})."
        ) from exc

    metrics_store.record_request(resultat["status"], time.perf_counter() - debut)
    return resultat, request_id


@app.get("/health", response_model=schemas.HealthResponse)
async def health(engine: RagEngine = Depends(get_engine)) -> schemas.HealthResponse:
    info = engine.health()
    return schemas.HealthResponse(version=API_VERSION, **info)


@app.get("/availability")
async def availability() -> dict:
    """Vérification légère : ne dépend PAS de `engine` (donc jamais de GPU,
    jamais de Qwen/BGE-M3). Sert uniquement en développement local, où un
    seul serveur répond à toutes les routes ; en production sur Modal, c'est
    la fonction availability() SÉPARÉE (modal_app.py) qui répond à ce même
    chemin, dans un conteneur CPU totalement indépendant du conteneur GPU."""
    return {"status": "ok", "service": "aftech-ai-platform-availability"}


@app.get(
    "/documents",
    response_model=list[schemas.DocumentItem],
    dependencies=[Depends(verify_api_key)],
)
async def list_documents(gestionnaire: DocumentManager = Depends(get_document_manager)) -> list[dict]:
    return gestionnaire.lister_tout()


@app.post(
    "/documents",
    response_model=schemas.DocumentUploadResponse,
    status_code=201,
    dependencies=[Depends(verify_api_key)],
)
async def upload_document(
    background_tasks: BackgroundTasks,
    fichier: UploadFile,
    gestionnaire: DocumentManager = Depends(get_document_manager),
) -> schemas.DocumentUploadResponse:
    contenu = await fichier.read()
    try:
        enregistrement = await gestionnaire.deposer(contenu, fichier.filename or "document.pdf")
    except FichierInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentDejaIndexe as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Extraction + indexation en tâche de fond : la réponse HTTP revient tout
    # de suite (statut UPLOADED), le client suit la progression via
    # GET /documents/{id} (EXTRACTING -> INDEXING -> READY/FAILED).
    background_tasks.add_task(gestionnaire.traiter, enregistrement.id)

    return schemas.DocumentUploadResponse(
        id=enregistrement.id, nom_original=enregistrement.nom_original, statut=enregistrement.statut
    )


@app.get(
    "/documents/{id_document}/status",
    response_model=schemas.DocumentStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def document_status(
    id_document: str, gestionnaire: DocumentManager = Depends(get_document_manager)
) -> schemas.DocumentStatusResponse:
    doc = gestionnaire.obtenir_statut(id_document)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    return schemas.DocumentStatusResponse(**doc)


@app.delete(
    "/documents/{id_document}",
    status_code=204,
    dependencies=[Depends(verify_api_key)],
)
async def delete_document(
    id_document: str, gestionnaire: DocumentManager = Depends(get_document_manager)
) -> None:
    try:
        await gestionnaire.supprimer(id_document)
    except DocumentIntrouvable as exc:
        raise HTTPException(status_code=404, detail="Document introuvable.") from exc
    except ReconstructionDejaEnCours as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/metrics", response_model=schemas.MetricsResponse, dependencies=[Depends(verify_api_key)])
async def get_metrics() -> dict:
    return metrics_store.snapshot()


@app.post("/ask", response_model=schemas.AskResponse, dependencies=[Depends(verify_api_key)])
async def ask(
    payload: schemas.AskRequest, engine: RagEngine = Depends(get_engine)
) -> schemas.AskResponse:
    resultat, request_id = _repondre_ou_erreur(
        engine, payload.question, payload.top_k, response_language=payload.response_language
    )
    return schemas.AskResponse(**resultat, request_id=request_id)


@app.post(
    "/v1/chat/completions",
    response_model=schemas.ChatCompletionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def chat_completions(
    payload: schemas.ChatCompletionRequest, engine: RagEngine = Depends(get_engine)
) -> schemas.ChatCompletionResponse:
    messages_user = [m for m in payload.messages if m.role == "user"]
    if not messages_user:
        raise HTTPException(status_code=400, detail="Aucun message 'user' trouvé.")

    question = messages_user[-1].content
    if len(question) > LIMITE_QUESTION_CARACTERES:
        raise HTTPException(
            status_code=400,
            detail=f"Message trop long ({len(question)} caractères, max {LIMITE_QUESTION_CARACTERES}).",
        )

    resultat, request_id = _repondre_ou_erreur(engine, question, top_k=8)

    return schemas.ChatCompletionResponse(
        id=f"chatcmpl-{request_id}",
        created=int(time.time()),
        model=payload.model,
        choices=[
            schemas.ChatCompletionChoice(
                index=0,
                message=schemas.ChatMessage(role="assistant", content=resultat["answer"]),
                finish_reason="stop",
            )
        ],
        usage=schemas.ChatCompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )
