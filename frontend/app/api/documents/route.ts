import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { DocumentItem } from "@/lib/types";

export async function GET() {
  const resultat = await appelerBackend<DocumentItem[]>("/documents");

  if (!resultat.ok) {
    return NextResponse.json({ message: resultat.message }, { status: resultat.status });
  }

  return NextResponse.json(resultat.data);
}
