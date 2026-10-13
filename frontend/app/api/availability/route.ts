import { NextResponse } from "next/server";

import { verifierDisponibilite } from "@/lib/backend";

// Route LÉGÈRE, CPU uniquement côté backend (fonction Modal "availability",
// SÉPARÉE du conteneur GPU "web" — voir backend/app/modal_app.py). C'est la
// SEULE route que BackendStatusIndicator est autorisé à appeler
// automatiquement (toutes les 30 s) : jamais /api/health, jamais /api/ask.
export async function GET() {
  const disponible = await verifierDisponibilite();
  return NextResponse.json({ disponible }, { status: disponible ? 200 : 503 });
}
