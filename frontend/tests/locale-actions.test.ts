import { describe, expect, it, vi } from "vitest";

// Préférence de langue persistée exigence : la Server Action écrit un cookie
// NON sensible (pas de donnée utilisateur, juste "fr"/"en"/"de"), lu ensuite
// par i18n/request.ts à chaque rendu — voir locale-request.test.ts pour la
// boucle complète (écriture -> lecture -> locale effective).
const cookieStoreMock = { set: vi.fn(), get: vi.fn() };
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => cookieStoreMock),
}));

describe("definirLocale (Server Action du LocaleSwitcher)", () => {
  it("écrit un cookie 'locale' non sensible pour une langue valide", async () => {
    const { definirLocale } = await import("@/lib/actions/locale");
    await definirLocale("de");

    expect(cookieStoreMock.set).toHaveBeenCalledWith(
      "locale",
      "de",
      expect.objectContaining({ sameSite: "lax" }),
    );
  });

  it("n'écrit RIEN pour une langue invalide (défense en profondeur côté serveur)", async () => {
    cookieStoreMock.set.mockClear();
    const { definirLocale } = await import("@/lib/actions/locale");
    // @ts-expect-error -- on force volontairement une valeur hors du type Locale
    await definirLocale("es");

    expect(cookieStoreMock.set).not.toHaveBeenCalled();
  });
});
