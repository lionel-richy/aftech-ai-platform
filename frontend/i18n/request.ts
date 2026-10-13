import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { resoudreLocaleDepuisCookie } from "@/i18n/config";

// Pas de routage par URL (pas de /fr/..., /en/...) : la préférence de langue
// vit uniquement dans un cookie non sensible ("locale"), lu ici pour que les
// composants serveur ET client reçoivent la bonne langue dès le rendu initial.
export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = resoudreLocaleDepuisCookie(store.get("locale")?.value);

  const messages = (await import(`../messages/${locale}.json`)).default;

  return { locale, messages };
});
