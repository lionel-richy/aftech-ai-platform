"use server";

import { cookies } from "next/headers";

import { estLocaleValide, type Locale } from "@/i18n/config";

// Cookie non sensible (pas de donnée utilisateur) : stocke uniquement la
// préférence de langue de l'interface. Appeler cette action depuis le client
// déclenche automatiquement un nouveau rendu des composants serveur avec la
// nouvelle langue — pas de router.refresh() manuel nécessaire.
export async function definirLocale(locale: Locale) {
  if (!estLocaleValide(locale)) return;
  const store = await cookies();
  store.set("locale", locale, { maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
}
