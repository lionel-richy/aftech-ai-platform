import { describe, expect, it } from "vitest";

import { expliquerErreurHttp } from "@/lib/errorMessages";

describe("expliquerErreurHttp", () => {
  it.each([401, 403])("401/403 -> authentification refusée, type 'erreur'", (status) => {
    const resultat = expliquerErreurHttp(status);
    expect(resultat.type).toBe("erreur");
    expect(resultat.titre.toLowerCase()).toContain("authentification");
  });

  it("422 -> question refusée, type 'erreur'", () => {
    const resultat = expliquerErreurHttp(422, "top_k doit être positif");
    expect(resultat.type).toBe("erreur");
    expect(resultat.description).toBe("top_k doit être positif");
  });

  it("503 -> backend indisponible, type 'indisponible'", () => {
    const resultat = expliquerErreurHttp(503);
    expect(resultat.type).toBe("indisponible");
    expect(resultat.titre.toLowerCase()).toContain("indisponible");
  });

  it("504 -> démarrage à froid, type 'indisponible', mentionne le délai", () => {
    const resultat = expliquerErreurHttp(504);
    expect(resultat.type).toBe("indisponible");
    expect(resultat.titre.toLowerCase()).toContain("froid");
    expect(resultat.description.toLowerCase()).toContain("minutes");
  });

  it("code inconnu -> message générique, type 'erreur'", () => {
    const resultat = expliquerErreurHttp(418, "je suis une théière");
    expect(resultat.type).toBe("erreur");
    expect(resultat.description).toBe("je suis une théière");
  });
});
