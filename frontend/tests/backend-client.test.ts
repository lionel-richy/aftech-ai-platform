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

describe("verifierDisponibilite (ping CPU, Partie 2)", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_AVAILABILITY_URL", "http://availability-test:9000");
    // Volontairement PAS de BACKEND_API_KEY ici : cette fonction ne doit
    // JAMAIS en avoir besoin (aucune information sensible renvoyée).
    vi.stubEnv("BACKEND_API_KEY", "");
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("appelle BACKEND_AVAILABILITY_URL + '/availability', JAMAIS BACKEND_BASE_URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    await verifierDisponibilite();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("http://availability-test:9000/availability");
  });

  it("n'ajoute JAMAIS d'en-tête Authorization (aucune clé nécessaire)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    await verifierDisponibilite();

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.headers).toBeUndefined();
  });

  it("fonctionne même sans BACKEND_API_KEY configurée (contrairement à appelerBackend)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renvoie false (jamais d'exception) quand l'API est injoignable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(false);
  });

  it("renvoie false quand la réponse n'est pas ok (ex. 503)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(false);
  });
});
