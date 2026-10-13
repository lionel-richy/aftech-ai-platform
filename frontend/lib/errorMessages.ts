// Explications simples pour chaque erreur que le proxy Next.js peut renvoyer.
// "type" détermine quel composant d'état visuel utiliser côté UI (voir
// components/ui/StateViews.tsx). Les textes réels vivent dans
// messages/{locale}.json (namespace "Errors") ; ce module ne renvoie que des
// clés, pour être utilisable aussi bien côté client que côté serveur.
import type { ApiErrorCode } from "./types";

type CleTitre = "authTitle" | "validationTitle" | "unavailableTitle" | "timeoutTitle" | "unknownTitle";
type CleDescription =
  | "authDescription"
  | "validationDefault"
  | "questionTooLong"
  | "serverMisconfigured"
  | "unavailableDefault"
  | "timeoutDescription"
  | "unknownDefault";

export interface ErreurExplicationCles {
  titreKey: CleTitre;
  titreValues?: Record<string, number>;
  descriptionKey: CleDescription;
  descriptionValues?: Record<string, number>;
  // Texte déjà résolu, affiché TEL QUEL au lieu de descriptionKey — réservé
  // au "detail" du VRAI backend (passthrough non traduit, comme une
  // citation). Jamais posé quand l'erreur vient de notre propre proxy
  // (voir CODE_VERS_EXPLICATION ci-dessous) : dans ce cas, descriptionKey
  // pilote toujours l'affichage, dans la langue active.
  descriptionOverride?: string;
  type: "indisponible" | "erreur";
}

// Erreurs générées par NOTRE proxy (voir lib/backend.ts et
// app/api/ask/route.ts) : toujours traduites via une clé, jamais via le
// champ "message" brut (qui reste en français, interne/log uniquement).
const CODE_VERS_EXPLICATION: Record<
  ApiErrorCode,
  (values?: Record<string, number>) => ErreurExplicationCles
> = {
  invalid_json: () => ({ titreKey: "validationTitle", descriptionKey: "validationDefault", type: "erreur" }),
  empty_question: () => ({ titreKey: "validationTitle", descriptionKey: "validationDefault", type: "erreur" }),
  question_too_long: (values) => ({
    titreKey: "validationTitle",
    descriptionKey: "questionTooLong",
    descriptionValues: values,
    type: "erreur",
  }),
  api_key_missing: () => ({
    titreKey: "unknownTitle",
    titreValues: { status: 500 },
    descriptionKey: "serverMisconfigured",
    type: "erreur",
  }),
  backend_error_status: (values) => ({
    titreKey: "unknownTitle",
    titreValues: values,
    descriptionKey: "unknownDefault",
    type: "erreur",
  }),
  timeout_no_response: () => ({ titreKey: "timeoutTitle", descriptionKey: "timeoutDescription", type: "indisponible" }),
  backend_unreachable: () => ({ titreKey: "unavailableTitle", descriptionKey: "unavailableDefault", type: "indisponible" }),
};

export function expliquerErreurHttp(
  status: number,
  messageBrut?: string,
  code?: ApiErrorCode,
  values?: Record<string, number>,
): ErreurExplicationCles {
  if (code) {
    return CODE_VERS_EXPLICATION[code](values);
  }

  // Pas de code : l'erreur vient du VRAI backend (ex. "detail" Pydantic sur
  // un 422 de response_language invalide). messageBrut est alors affiché
  // tel quel, sans traduction — exactement comme une citation.
  switch (status) {
    case 401:
    case 403:
      return { titreKey: "authTitle", descriptionKey: "authDescription", type: "erreur" };
    case 422:
      return {
        titreKey: "validationTitle",
        descriptionKey: "validationDefault",
        descriptionOverride: messageBrut,
        type: "erreur",
      };
    case 503:
      return {
        titreKey: "unavailableTitle",
        descriptionKey: "unavailableDefault",
        descriptionOverride: messageBrut,
        type: "indisponible",
      };
    case 504:
      return { titreKey: "timeoutTitle", descriptionKey: "timeoutDescription", type: "indisponible" };
    default:
      return {
        titreKey: "unknownTitle",
        titreValues: { status },
        descriptionKey: "unknownDefault",
        descriptionOverride: messageBrut,
        type: "erreur",
      };
  }
}

// Explication courte du statut d'une réponse /ask, affichée sous le badge.
export const EXPLICATION_STATUT_KEYS: Record<
  "COMPLETE" | "PARTIAL" | "NOT_FOUND",
  "explicationComplete" | "explicationPartial" | "explicationNotFound"
> = {
  COMPLETE: "explicationComplete",
  PARTIAL: "explicationPartial",
  NOT_FOUND: "explicationNotFound",
};
