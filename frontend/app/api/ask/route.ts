import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { AskResponse } from "@/lib/types";

const LIMITE_QUESTION_CARACTERES = 2000;

export async function POST(request: Request) {
  let corps: { question?: unknown; top_k?: unknown };
  try {
    corps = await request.json();
  } catch {
    return NextResponse.json({ message: "Corps de requête JSON invalide." }, { status: 400 });
  }

  const question = typeof corps.question === "string" ? corps.question : "";
  if (!question.trim()) {
    return NextResponse.json({ message: "La question est vide." }, { status: 400 });
  }
  if (question.length > LIMITE_QUESTION_CARACTERES) {
    return NextResponse.json(
      { message: `Question trop longue (max ${LIMITE_QUESTION_CARACTERES} caractères).` },
      { status: 400 },
    );
  }

  const resultat = await appelerBackend<AskResponse>("/ask", {
    methode: "POST",
    corps: { question, top_k: typeof corps.top_k === "number" ? corps.top_k : 8 },
    // Au moins 300 s : un démarrage à froid Modal (téléchargement + chargement
    // de Qwen sur un conteneur GPU neuf) peut prendre plusieurs minutes.
    timeoutMs: 300000,
  });

  if (!resultat.ok) {
    return NextResponse.json({ message: resultat.message }, { status: resultat.status });
  }

  return NextResponse.json(resultat.data);
}
