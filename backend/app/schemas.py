"""Schémas Pydantic (contrats d'entrée/sortie de l'API). Un seul endroit pour
savoir exactement ce que l'API accepte et renvoie."""

from typing import List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)


class SourceItem(BaseModel):
    fichier: str
    page: int
    extrait: str
    score: float


class ValidatedClaim(BaseModel):
    affirmation: str
    fichier: Optional[str] = None
    page: Optional[int] = None
    citation: str
    citation_presente: bool
    preuve_supported: bool


class Timings(BaseModel):
    recherche_secondes: float
    generation_secondes: float
    total_secondes: float


class AskResponse(BaseModel):
    answer: str
    status: str  # "COMPLETE" | "PARTIAL" | "NOT_FOUND"
    sources: List[SourceItem]
    validated_claims: List[ValidatedClaim]
    timings: Timings
    request_id: str


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    ready: bool
    llm_model: str
    embedding_model: str
    gpu: str
    # None si aucun GPU (mode dégradé) : jamais un 0 qui laisserait croire à
    # une vraie mesure.
    vram_totale_octets: Optional[int] = None
    vram_utilisee_octets: Optional[int] = None
    documents_count: int
    chunks_count: int


class DocumentItem(BaseModel):
    nom_fichier: str
    pages: int
    passages: int
    hash_sha256: str
    modele_embeddings: str
    date_index: str


class MetricsResponse(BaseModel):
    uptime_secondes: float
    requests_total: int
    status_complete: int
    status_partial: int
    status_not_found: int
    errors_total: int
    latence_moyenne_secondes: Optional[float] = None


# --- Compatibilité OpenAI (sous-ensemble, voir docs/BACKEND_GUIDE.md) ---


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage
