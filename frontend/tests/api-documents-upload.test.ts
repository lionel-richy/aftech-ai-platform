import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { GET, POST } from "@/app/api/documents/route";

// jsdom (environnement de test) et le "Request" natif de Node (utilisé par
// next/server) ont des implémentations de FormData/File incompatibles entre
// elles (bug d'interop connu, pas spécifique à ce projet) : construire un
// vrai FormData PUIS le passer comme corps d'un vrai Request échoue avec une
// erreur WebIDL interne, y compris en dehors de tout code applicatif. On
// contourne en simulant directement .formData() plutôt qu'en sérialisant un
// Request réel — ce que request.formData() renvoie EST un vrai FormData
// jsdom, donc `instanceof Blob`/`.size` côté route.ts restent testés pour de vrai.
function requeteAvecFichier(nom: string, contenu: string, type = "application/pdf") {
  const formulaire = new FormData();
  formulaire.append("fichier", new File([contenu], nom, { type }));
  return { formData: async () => formulaire } as unknown as Request;
}

describe("POST /api/documents (proxy upload)", () => {
  it("rejette une requête sans fichier, avec code='no_file', SANS appeler le backend", async () => {
    const requete = { formData: async () => new FormData() } as unknown as Request;

    const reponse = await POST(requete);
    const corps = await reponse.json();

    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("no_file");
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("transmet le FormData tel quel à appelerBackend (pas de JSON.stringify)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { id: "abc", nom_original: "rapport.pdf", statut: "UPLOADED" },
    });

    const reponse = await POST(requeteAvecFichier("rapport.pdf", "contenu-pdf"));
    const corps = await reponse.json();

    expect(reponse.status).toBe(201);
    expect(corps.statut).toBe("UPLOADED");
    expect(appelerBackend).toHaveBeenCalledWith(
      "/documents",
      expect.objectContaining({ methode: "POST", corps: expect.any(FormData) }),
    );
  });

  it("relaie un 422 (fichier invalide côté backend) avec son code", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 422,
      message: "Le fichier PDF est corrompu ou illisible.",
    });

    const reponse = await POST(requeteAvecFichier("corrompu.pdf", "xx"));
    expect(reponse.status).toBe(422);
  });

  it("relaie un 409 (doublon détecté par le backend)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 409,
      message: "Ce document (même contenu) est déjà indexé.",
    });

    const reponse = await POST(requeteAvecFichier("copie.pdf", "contenu-pdf"));
    expect(reponse.status).toBe(409);
  });
});

describe("GET /api/documents (liste, inchangé)", () => {
  it("relaie la liste telle quelle", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: [] });
    const reponse = await GET();
    expect(reponse.status).toBe(200);
    expect(await reponse.json()).toEqual([]);
  });
});
