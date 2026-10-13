import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  verifierDisponibilite: vi.fn(),
}));

import { verifierDisponibilite } from "@/lib/backend";
import { GET } from "@/app/api/availability/route";

describe("GET /api/availability (route légère, CPU uniquement côté backend)", () => {
  it("renvoie 200 et disponible=true quand verifierDisponibilite() réussit", async () => {
    vi.mocked(verifierDisponibilite).mockResolvedValue(true);

    const reponse = await GET();
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.disponible).toBe(true);
  });

  it("renvoie 503 et disponible=false quand verifierDisponibilite() échoue", async () => {
    vi.mocked(verifierDisponibilite).mockResolvedValue(false);

    const reponse = await GET();
    const corps = await reponse.json();

    expect(reponse.status).toBe(503);
    expect(corps.disponible).toBe(false);
  });
});
