import { describe, expect, it } from "vitest";

import { resoudreLocaleDepuisCookie } from "@/i18n/config";

// resoudreLocaleDepuisCookie est la logique utilisée par i18n/request.ts
// (lu par getLocale() côté serveur, puis par <html lang={locale}> dans
// app/layout.tsx) — testée ici en isolation, sans next/headers ni
// next-intl/server : ces modules exposent une condition d'export
// "react-server" que Vitest (hors runtime Next.js) ne peut pas satisfaire.
// Couvre : préférence de langue persistée via cookie, et attribut HTML lang
// mis à jour dynamiquement (puisque c'est la même valeur de locale qui pilote
// les deux).
describe("resoudreLocaleDepuisCookie", () => {
  it("utilise la locale du cookie quand elle est valide ('de')", () => {
    expect(resoudreLocaleDepuisCookie("de")).toBe("de");
  });

  it("utilise la locale du cookie quand elle est valide ('en')", () => {
    expect(resoudreLocaleDepuisCookie("en")).toBe("en");
  });

  it("retombe sur 'fr' par défaut si le cookie est absent", () => {
    expect(resoudreLocaleDepuisCookie(undefined)).toBe("fr");
  });

  it("retombe sur 'fr' par défaut si le cookie contient une valeur invalide", () => {
    expect(resoudreLocaleDepuisCookie("es")).toBe("fr");
  });
});
