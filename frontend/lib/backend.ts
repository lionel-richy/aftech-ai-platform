// SERVEUR UNIQUEMENT. Ce fichier lit BACKEND_API_KEY (jamais NEXT_PUBLIC_) et
// ne doit être importé QUE depuis app/api/*/route.ts (routes serveur Next.js).
// Le navigateur appelle toujours nos routes /api/*, jamais Modal/le backend directement.
//
// Variables d'environnement (frontend/.env.local, jamais commité) :
//   BACKEND_BASE_URL  ex. https://<workspace>--aftech-ai-platform-web.modal.run
//   BACKEND_API_KEY   même valeur que le secret Modal "aftech-backend-secrets"
import "server-only";

import type { BackendResult } from "./types";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

interface AppelBackendOptions {
  methode?: "GET" | "POST";
  corps?: unknown;
  authentifie?: boolean; // false pour /health, qui ne demande pas de clé
  timeoutMs?: number;
}

export async function appelerBackend<T>(
  chemin: string,
  options: AppelBackendOptions = {},
): Promise<BackendResult<T>> {
  const { methode = "GET", corps, authentifie = true, timeoutMs = 15000 } = options;

  if (authentifie && !BACKEND_API_KEY) {
    return {
      ok: false,
      status: 500,
      code: "api_key_missing",
      message: "BACKEND_API_KEY n'est pas configurée côté serveur Next.js.",
    };
  }

  const entetes: Record<string, string> = { "Content-Type": "application/json" };
  if (authentifie) {
    entetes.Authorization = `Bearer ${BACKEND_API_KEY}`;
  }

  const controleur = new AbortController();
  const minuteur = setTimeout(() => controleur.abort(), timeoutMs);

  try {
    const reponse = await fetch(`${BACKEND_BASE_URL}${chemin}`, {
      method: methode,
      headers: entetes,
      body: corps !== undefined ? JSON.stringify(corps) : undefined,
      signal: controleur.signal,
      cache: "no-store",
    });

    if (!reponse.ok) {
      let message = `Le backend a répondu ${reponse.status}.`;
      // "code" n'est posé QUE pour le message générique ci-dessus (que NOUS
      // générons) : si le backend a renvoyé son propre "detail", ce texte
      // reste un passthrough non traduit (comme une citation), sans code.
      let code: "backend_error_status" | undefined = "backend_error_status";
      try {
        const corpsErreur = await reponse.json();
        if (typeof corpsErreur?.detail === "string") {
          message = corpsErreur.detail;
          code = undefined;
        }
      } catch {
        // Corps non-JSON : on garde le message générique ci-dessus.
      }
      return { ok: false, status: reponse.status, message, code, values: code ? { status: reponse.status } : undefined };
    }

    const donnees = (await reponse.json()) as T;
    return { ok: true, data: donnees };
  } catch (erreur) {
    const estTimeout = erreur instanceof Error && erreur.name === "AbortError";
    // 504 (timeout) et 503 (injoignable) sont volontairement distincts : le
    // frontend affiche une explication différente selon le cas (voir
    // lib/errorMessages.ts) — un démarrage à froid qui traîne n'est pas la
    // même situation qu'un backend complètement arrêté.
    return {
      ok: false,
      status: estTimeout ? 504 : 503,
      code: estTimeout ? "timeout_no_response" : "backend_unreachable",
      message: estTimeout
        ? "Le backend n'a pas répondu à temps (démarrage à froid trop long ?)."
        : "Impossible de contacter le backend (indisponible ?).",
    };
  } finally {
    clearTimeout(minuteur);
  }
}
