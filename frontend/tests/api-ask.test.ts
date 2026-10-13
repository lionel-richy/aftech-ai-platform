import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { POST } from "@/app/api/ask/route";
import type { AskResponse } from "@/lib/types";

function requeteJson(corps: unknown) {
  return new Request("http://localhost/api/ask", {
    method: "POST",
    body: JSON.stringify(corps),
    headers: { "Content-Type": "application/json" },
  });
}

const REPONSE_COMPLETE: AskResponse = {
  answer: "14 caractères minimum.",
  status: "COMPLETE",
  sources: [],
  validated_claims: [],
  timings: { recherche_secondes: 0.1, generation_secondes: 1.2, total_secondes: 1.3 },
  request_id: "abc-123",
};

describe("POST /api/ask", () => {
  it("rejette une question vide SANS appeler le backend", async () => {
    const reponse = await POST(requeteJson({ question: "" }));
    expect(reponse.status).toBe(400);
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("rejette une question de plus de 2000 caractères SANS appeler le backend", async () => {
    const reponse = await POST(requeteJson({ question: "a".repeat(2001) }));
    expect(reponse.status).toBe(400);
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("relaie un statut COMPLETE tel quel", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    const reponse = await POST(requeteJson({ question: "Quelle est la longueur minimale ?" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.status).toBe("COMPLETE");
  });

  it("relaie un statut PARTIAL tel quel", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { ...REPONSE_COMPLETE, status: "PARTIAL" },
    });

    const reponse = await POST(requeteJson({ question: "Quels sont les chantiers ?" }));
    const corps = await reponse.json();
    expect(corps.status).toBe("PARTIAL");
  });

  it("relaie un statut NOT_FOUND tel quel", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { ...REPONSE_COMPLETE, status: "NOT_FOUND", answer: "Information non trouvée dans les documents." },
    });

    const reponse = await POST(requeteJson({ question: "Quel est le CA d'AFTECH ?" }));
    const corps = await reponse.json();
    expect(corps.status).toBe("NOT_FOUND");
  });

  it("relaie un 503 backend indisponible SANS traceback", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 503,
      message: "Impossible de contacter le backend (indisponible ?).",
    });

    const reponse = await POST(requeteJson({ question: "Bonjour ?" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(503);
    expect(corps.message).not.toMatch(/Traceback/i);
  });
});
