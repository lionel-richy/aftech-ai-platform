import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { GET } from "@/app/api/documents/[id]/status/route";
import { DELETE } from "@/app/api/documents/[id]/route";

function requeteAvecParams(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("GET /api/documents/[id]/status", () => {
  it("appelle le backend sur le bon chemin encodé", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: {
        id: "abc 123",
        nom_original: "x.pdf",
        statut: "READY",
        message_erreur: null,
        nb_pages: 1,
        nb_passages: 2,
        date_ajout: "2026-01-01T00:00:00Z",
      },
    });

    const reponse = await GET(new Request("http://localhost"), requeteAvecParams("abc 123"));
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.statut).toBe("READY");
    expect(appelerBackend).toHaveBeenCalledWith("/documents/abc%20123/status");
  });

  it("relaie un 404 (document introuvable)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: false, status: 404, message: "Document introuvable." });

    const reponse = await GET(new Request("http://localhost"), requeteAvecParams("inconnu"));
    expect(reponse.status).toBe(404);
  });
});

describe("DELETE /api/documents/[id]", () => {
  it("renvoie 204 sans corps quand la suppression réussit", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: undefined });

    const reponse = await DELETE(new Request("http://localhost"), requeteAvecParams("abc123"));

    expect(reponse.status).toBe(204);
    expect(appelerBackend).toHaveBeenCalledWith(
      "/documents/abc123",
      expect.objectContaining({ methode: "DELETE" }),
    );
  });

  it("relaie un 409 (reconstruction déjà en cours)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 409,
      message: "Une reconstruction d'index est déjà en cours — réessayez dans un instant.",
    });

    const reponse = await DELETE(new Request("http://localhost"), requeteAvecParams("abc123"));
    expect(reponse.status).toBe(409);
  });
});
