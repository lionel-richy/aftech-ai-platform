import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { AskResponse } from "@/lib/types";

const LIMITE_QUESTION_CARACTERES = 2000;

export async function POST(request: Request) {
  let corps: { question?: unknown; top_k?: unknown; response_language?: unknown };
  try {
    corps = await request.json();
  } catch {
    // "message" reste en français (log/debug uniquement) : c'est "code" qui
    // pilote le texte traduit affiché côté client (voir lib/errorMessages.ts).
    return NextResponse.json(
      { message: "Corps de requête JSON invalide.", code: "invalid_json" },
      { status: 400 },
    );
  }

  const question = typeof corps.question === "string" ? corps.question : "";
  if (!question.trim()) {
    return NextResponse.json({ message: "La question est vide.", code: "empty_question" }, { status: 400 });
  }
  if (question.length > LIMITE_QUESTION_CARACTERES) {
    return NextResponse.json(
      {
        message: `Question trop longue (max ${LIMITE_QUESTION_CARACTERES} caractères).`,
        code: "question_too_long",
        values: { max: LIMITE_QUESTION_CARACTERES },
      },
      { status: 400 },
    );
  }

  // response_language n'est PAS revalidé ici : le backend (schemas.py,
  // AskRequest.response_language: Literal["fr","en","de"]) est la seule
  // source de vérité et renvoie 422 si la valeur est invalide — ce proxy se
  // contente de transmettre, avec "fr" par défaut si absent.
  const resultat = await appelerBackend<AskResponse>("/ask", {
    methode: "POST",
    corps: {
      question,
      top_k: typeof corps.top_k === "number" ? corps.top_k : 8,
      response_language: typeof corps.response_language === "string" ? corps.response_language : "fr",
    },
    // Au moins 300 s : un démarrage à froid Modal (téléchargement + chargement
    // de Qwen sur un conteneur GPU neuf) peut prendre plusieurs minutes.
    timeoutMs: 300000,
  });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}
