import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// lib/backend.ts importe "server-only", qui lance volontairement une erreur
// quand résolu avec la condition "browser" (le cas dans l'environnement
// jsdom global de ce projet, utilisé pour les tests de composants). On
// remplace donc ce module par un no-op pour CE fichier, qui teste la
// logique de lib/backend.ts, pas le garde-fou de bundling lui-même.
vi.mock("server-only", () => ({}));

const CLE_TEST = "cle-secrete-de-test-ne-jamais-exposer";

describe("appelerBackend (client serveur -> FastAPI)", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_BASE_URL", "http://backend-test:8000");
    vi.stubEnv("BACKEND_API_KEY", CLE_TEST);
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("ajoute l'en-tête Authorization avec la clé serveur", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    await appelerBackend("/documents");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe(`Bearer ${CLE_TEST}`);
  });

  it("n'ajoute PAS l'en-tête Authorization quand authentifie=false (/health)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    await appelerBackend("/health", { authentifie: false });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("renvoie une erreur 503 et ne lève pas d'exception quand le backend est injoignable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("fetch failed")));

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/ask", { methode: "POST", corps: { question: "x" } });

    expect(resultat.ok).toBe(false);
    if (!resultat.ok) {
      expect(resultat.status).toBe(503);
      expect(resultat.message.toLowerCase()).toContain("backend");
    }
  });

  it("renvoie 504 (pas 503) quand la requête expire (timeout, démarrage à froid)", async () => {
    const erreurAbort = new Error("The operation was aborted");
    erreurAbort.name = "AbortError";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(erreurAbort));

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/ask", { methode: "POST", corps: { question: "x" }, timeoutMs: 10 });

    expect(resultat.ok).toBe(false);
    if (!resultat.ok) {
      expect(resultat.status).toBe(504);
      expect(resultat.message.toLowerCase()).toContain("temps");
    }
  });

  it("refuse l'appel si BACKEND_API_KEY n'est pas configurée", async () => {
    vi.stubEnv("BACKEND_API_KEY", "");
    vi.resetModules();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/documents");

    expect(resultat.ok).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
