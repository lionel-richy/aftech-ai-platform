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

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import schemas
from .metrics import metrics_store
from .rag_engine import BackendUnavailable, RagEngine
from .security import get_cors_origins, verify_api_key

API_VERSION = "0.1.0"
LIMITE_QUESTION_CARACTERES = 2000


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chargement UNE SEULE FOIS par conteneur/process, avant de servir la
    # moindre requête (donc /health ne déclenche jamais ce chargement).
    engine = RagEngine()
    engine.load()
    app.state.engine = engine
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


@app.get(
    "/documents",
    response_model=list[schemas.DocumentItem],
    dependencies=[Depends(verify_api_key)],
)
async def list_documents(engine: RagEngine = Depends(get_engine)) -> list[dict]:
    return engine.documents()


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
