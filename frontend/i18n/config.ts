export const LOCALES = ["fr", "en", "de"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_PAR_DEFAUT: Locale = "fr";

// Mappage vers une locale BCP 47 complète, pour Intl.DateTimeFormat /
// Intl.NumberFormat (dates et nombres affichés selon la langue choisie).
export const LOCALE_BCP47: Record<Locale, string> = {
  fr: "fr-FR",
  en: "en-US",
  de: "de-DE",
};

export function estLocaleValide(valeur: string): valeur is Locale {
  return (LOCALES as readonly string[]).includes(valeur);
}

// Fonction pure (pas d'import next/headers ni next-intl/server) : testable
// directement sans contexte Next.js, et partagée par i18n/request.ts (lecture
// du cookie "locale" côté serveur).
export function resoudreLocaleDepuisCookie(valeurCookie: string | undefined): Locale {
  if (valeurCookie !== undefined && estLocaleValide(valeurCookie)) return valeurCookie;
  return LOCALE_PAR_DEFAUT;
}
