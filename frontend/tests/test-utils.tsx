// Enveloppe de rendu partagée par les tests de composants : fournit le
// contexte next-intl (useTranslations/useLocale lèvent sans lui). Les
// messages réels de messages/{locale}.json sont utilisés directement — une
// seule source de vérité, les tests ne dupliquent jamais les traductions.
import type { ReactElement, ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Locale } from "@/i18n/config";
import fr from "@/messages/fr.json";
import en from "@/messages/en.json";
import de from "@/messages/de.json";

const MESSAGES_PAR_LOCALE: Record<Locale, typeof fr> = { fr, en, de };

export function renderAvecIntl(
  ui: ReactElement,
  { locale = "fr" as Locale, ...options }: { locale?: Locale } & Omit<RenderOptions, "wrapper"> = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES_PAR_LOCALE[locale]}>
        {children}
      </NextIntlClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}
