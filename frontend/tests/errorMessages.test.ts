import { describe, expect, it } from "vitest";

import { expliquerErreurHttp } from "@/lib/errorMessages";

// expliquerErreurHttp renvoie des CLÉS de traduction (namespace "Errors"),
// jamais du texte résolu : les composants appellent t(cle) eux-mêmes (voir
// ChatView.tsx). Ce module reste utilisable aussi bien côté client que
// serveur, sans dépendre d'un contexte next-intl.
describe("expliquerErreurHttp", () => {
  it.each([401, 403])("401/403 -> authTitle, type 'erreur'", (status) => {
    const resultat = expliquerErreurHttp(status);
    expect(resultat.type).toBe("erreur");
    expect(resultat.titreKey).toBe("authTitle");
  });

  it("422 -> validationTitle, type 'erreur', description surchargée par le backend", () => {
    const resultat = expliquerErreurHttp(422, "top_k doit être positif");
    expect(resultat.type).toBe("erreur");
    expect(resultat.titreKey).toBe("validationTitle");
    expect(resultat.descriptionOverride).toBe("top_k doit être positif");
  });

  it("503 -> unavailableTitle, type 'indisponible'", () => {
    const resultat = expliquerErreurHttp(503);
    expect(resultat.type).toBe("indisponible");
    expect(resultat.titreKey).toBe("unavailableTitle");
  });

  it("504 -> timeoutTitle, type 'indisponible'", () => {
    const resultat = expliquerErreurHttp(504);
    expect(resultat.type).toBe("indisponible");
    expect(resultat.titreKey).toBe("timeoutTitle");
    expect(resultat.descriptionKey).toBe("timeoutDescription");
  });

  it("code inconnu -> unknownTitle avec le code en valeur d'interpolation, type 'erreur'", () => {
    const resultat = expliquerErreurHttp(418, "je suis une théière");
    expect(resultat.type).toBe("erreur");
    expect(resultat.titreKey).toBe("unknownTitle");
    expect(resultat.titreValues).toEqual({ status: 418 });
    expect(resultat.descriptionOverride).toBe("je suis une théière");
  });

  // Erreurs générées par NOTRE proxy (code présent) : toujours une clé de
  // traduction, JAMAIS le "message" brut (français, interne/log uniquement)
  // — c'est ce qui permet de respecter la langue active (fr/en/de).
  it("code='empty_question' -> validationDefault, sans descriptionOverride (message ignoré)", () => {
    const resultat = expliquerErreurHttp(400, "La question est vide.", "empty_question");
    expect(resultat.titreKey).toBe("validationTitle");
    expect(resultat.descriptionKey).toBe("validationDefault");
    expect(resultat.descriptionOverride).toBeUndefined();
  });

  it("code='invalid_json' -> validationDefault", () => {
    const resultat = expliquerErreurHttp(400, "Corps de requête JSON invalide.", "invalid_json");
    expect(resultat.descriptionKey).toBe("validationDefault");
    expect(resultat.descriptionOverride).toBeUndefined();
  });

  it("code='question_too_long' -> questionTooLong avec values.max transmis", () => {
    const resultat = expliquerErreurHttp(400, "Question trop longue (max 2000 caractères).", "question_too_long", {
      max: 2000,
    });
    expect(resultat.descriptionKey).toBe("questionTooLong");
    expect(resultat.descriptionValues).toEqual({ max: 2000 });
    expect(resultat.descriptionOverride).toBeUndefined();
  });

  it("code='api_key_missing' -> serverMisconfigured, titre avec status=500", () => {
    const resultat = expliquerErreurHttp(500, "BACKEND_API_KEY n'est pas configurée.", "api_key_missing");
    expect(resultat.titreKey).toBe("unknownTitle");
    expect(resultat.titreValues).toEqual({ status: 500 });
    expect(resultat.descriptionKey).toBe("serverMisconfigured");
  });

  it("code='backend_error_status' -> unknownDefault avec le status transmis", () => {
    const resultat = expliquerErreurHttp(502, "Le backend a répondu 502.", "backend_error_status", { status: 502 });
    expect(resultat.titreValues).toEqual({ status: 502 });
    expect(resultat.descriptionKey).toBe("unknownDefault");
  });

  it("code='timeout_no_response' -> timeoutTitle/timeoutDescription (réutilise les clés existantes)", () => {
    const resultat = expliquerErreurHttp(504, "Le backend n'a pas répondu à temps.", "timeout_no_response");
    expect(resultat.titreKey).toBe("timeoutTitle");
    expect(resultat.descriptionKey).toBe("timeoutDescription");
    expect(resultat.type).toBe("indisponible");
  });

  it("code='backend_unreachable' -> unavailableTitle/unavailableDefault (réutilise les clés existantes)", () => {
    const resultat = expliquerErreurHttp(503, "Impossible de contacter le backend.", "backend_unreachable");
    expect(resultat.titreKey).toBe("unavailableTitle");
    expect(resultat.descriptionKey).toBe("unavailableDefault");
    expect(resultat.type).toBe("indisponible");
  });
});
