// Explications simples pour chaque code d'erreur que le proxy Next.js peut
// renvoyer. "type" détermine quel composant d'état visuel utiliser côté UI
// (voir components/ui/StateViews.tsx).

export interface ErreurExpliquee {
  titre: string;
  description: string;
  type: "indisponible" | "erreur";
}

export function expliquerErreurHttp(status: number, messageBrut?: string): ErreurExpliquee {
  switch (status) {
    case 401:
    case 403:
      return {
        titre: "Authentification refusée",
        description:
          "Le backend a refusé la clé API. Vérifiez BACKEND_API_KEY côté serveur Next.js (frontend/.env.local).",
        type: "erreur",
      };
    case 422:
      return {
        titre: "Question refusée par le backend",
        description: messageBrut || "Le format de la question n'a pas été accepté.",
        type: "erreur",
      };
    case 503:
      return {
        titre: "Backend indisponible",
        description:
          messageBrut ||
          "Le backend ne répond pas (pas de GPU disponible, ou service arrêté).",
        type: "indisponible",
      };
    case 504:
      return {
        titre: "Démarrage à froid trop long",
        description:
          "Le moteur IA n'a pas démarré à temps. Un premier appel après inactivité peut prendre plusieurs minutes — réessayez dans un instant.",
        type: "indisponible",
      };
    default:
      return {
        titre: `Erreur inattendue (${status})`,
        description: messageBrut || "Une erreur imprévue est survenue.",
        type: "erreur",
      };
  }
}

// Explication courte du statut d'une réponse /ask, affichée sous le badge.
export const EXPLICATION_STATUT: Record<"COMPLETE" | "PARTIAL" | "NOT_FOUND", string> = {
  COMPLETE: "Toutes les affirmations de la réponse ont été vérifiées dans les documents.",
  PARTIAL: "Seule une partie des affirmations a pu être vérifiée — des éléments peuvent manquer.",
  NOT_FOUND: "Aucune affirmation vérifiable n'a été trouvée dans les documents indexés.",
};
