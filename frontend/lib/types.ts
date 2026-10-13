// Types alignés EXACTEMENT sur backend/app/schemas.py — une seule source de
// vérité côté backend, ce fichier ne fait que la refléter côté frontend.

export type AnswerStatus = "COMPLETE" | "PARTIAL" | "NOT_FOUND";

// Doit rester identique à i18n/config.ts (Locale) et à
// backend/app/schemas.py (AskRequest.response_language).
export type ResponseLanguage = "fr" | "en" | "de";

export interface AskRequest {
  question: string;
  top_k?: number;
  response_language?: ResponseLanguage;
}

export interface SourceItem {
  fichier: string;
  page: number;
  extrait: string;
  score: number;
}

export interface ValidatedClaim {
  affirmation: string;
  fichier: string | null;
  page: number | null;
  citation: string;
  citation_presente: boolean;
  preuve_supported: boolean;
}

export interface Timings {
  recherche_secondes: number;
  generation_secondes: number;
  total_secondes: number;
}

export interface AskResponse {
  answer: string;
  status: AnswerStatus;
  sources: SourceItem[];
  validated_claims: ValidatedClaim[];
  timings: Timings;
  request_id: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  ready: boolean;
  llm_model: string;
  embedding_model: string;
  gpu: string;
  // null si aucun GPU (mode dégradé) : jamais un 0 qui laisserait croire à une vraie mesure.
  vram_totale_octets: number | null;
  vram_utilisee_octets: number | null;
  documents_count: number;
  chunks_count: number;
}

export interface DocumentItem {
  nom_fichier: string;
  pages: number;
  passages: number;
  hash_sha256: string;
  modele_embeddings: string;
  date_index: string;
}

export interface MetricsResponse {
  uptime_secondes: number;
  requests_total: number;
  status_complete: number;
  status_partial: number;
  status_not_found: number;
  errors_total: number;
  latence_moyenne_secondes: number | null;
}

// Code stable identifiant une erreur générée par NOTRE proxy (jamais le texte
// "detail" renvoyé par le vrai backend, qui reste un passthrough non traduit
// — comme une citation). Permet au client de choisir la bonne traduction
// (messages/{locale}.json, namespace "Errors") plutôt que d'afficher le
// champ "message" (français, interne/log uniquement) tel quel.
export type ApiErrorCode =
  | "invalid_json"
  | "empty_question"
  | "question_too_long"
  | "api_key_missing"
  | "backend_error_status"
  | "timeout_no_response"
  | "backend_unreachable";

// Résultat d'un appel proxy côté serveur Next.js : soit les données, soit une
// erreur typée (jamais de throw silencieux côté composants). "message" reste
// en français (log/debug uniquement) ; "code"/"values", quand présents,
// pilotent l'affichage traduit côté client (voir lib/errorMessages.ts).
export type BackendResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; code?: ApiErrorCode; values?: Record<string, number> };
