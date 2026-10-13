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
  it("rejette une question vide SANS appeler le backend, avec code='empty_question'", async () => {
    const reponse = await POST(requeteJson({ question: "" }));
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("empty_question");
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("rejette une question de plus de 2000 caractères, avec code='question_too_long' et values.max", async () => {
    const reponse = await POST(requeteJson({ question: "a".repeat(2001) }));
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("question_too_long");
    expect(corps.values).toEqual({ max: 2000 });
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("rejette un corps JSON invalide, avec code='invalid_json'", async () => {
    const requete = new Request("http://localhost/api/ask", {
      method: "POST",
      body: "{ceci n'est pas du json",
      headers: { "Content-Type": "application/json" },
    });
    const reponse = await POST(requete);
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("invalid_json");
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

  it("transmet response_language='de' au backend tel quel", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    await POST(requeteJson({ question: "Welches Dokument?", response_language: "de" }));

    expect(appelerBackend).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ corps: expect.objectContaining({ response_language: "de" }) }),
    );
  });

  it("défaut response_language='fr' si absent de la requête", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    await POST(requeteJson({ question: "Bonjour ?" }));

    expect(appelerBackend).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ corps: expect.objectContaining({ response_language: "fr" }) }),
    );
  });

  it("relaie un 422 (langue invalide refusée par le backend) SANS le transformer", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 422,
      message: "response_language: valeur non autorisée",
    });

    const reponse = await POST(requeteJson({ question: "Bonjour ?", response_language: "es" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(422);
    expect(corps.message).toContain("response_language");
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

  it("relaie le code et les values d'une erreur venant de lib/backend.ts (ex. 'backend_unreachable')", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 503,
      message: "Impossible de contacter le backend (indisponible ?).",
      code: "backend_unreachable",
    });

    const reponse = await POST(requeteJson({ question: "Bonjour ?" }));
    const corps = await reponse.json();

    expect(corps.code).toBe("backend_unreachable");
  });
});
