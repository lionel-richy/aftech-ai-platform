import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { DocumentItem, DocumentUploadResponse } from "@/lib/types";

export async function GET() {
  const resultat = await appelerBackend<DocumentItem[]>("/documents");

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}

export async function POST(request: Request) {
  const formulaire = await request.formData();
  const fichier = formulaire.get("fichier");

  if (!(fichier instanceof Blob) || !fichier.size) {
    return NextResponse.json({ message: "Aucun fichier reçu.", code: "no_file" }, { status: 400 });
  }

  // On ne revalide PAS le type/la signature ici : le backend (pypdf +
  // vérification binaire réelle, voir document_pipeline.py) est la seule
  // source de vérité, exactement comme response_language pour /ask.
  const resultat = await appelerBackend<DocumentUploadResponse>("/documents", {
    methode: "POST",
    corps: formulaire,
    timeoutMs: 60000,
  });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data, { status: 201 });
}
