// Preuve de bout en bout : une erreur de PROXY (code="question_too_long",
// "backend_unreachable", etc.) s'affiche réellement traduite dans les 3
// langues, pas seulement "la bonne clé est choisie" (déjà couvert dans
// errorMessages.test.ts).
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useTranslations } from "next-intl";

import { expliquerErreurHttp } from "@/lib/errorMessages";
import type { Locale } from "@/i18n/config";
import { renderAvecIntl } from "./test-utils";

function ErreurRendue({ status, code, values }: { status: number; code: Parameters<typeof expliquerErreurHttp>[2]; values?: Record<string, number> }) {
  const t = useTranslations("Errors");
  const explication = expliquerErreurHttp(status, "message interne français, jamais affiché", code, values);
  return (
    <>
      <p data-testid="titre">{t(explication.titreKey, explication.titreValues)}</p>
      <p data-testid="description">{t(explication.descriptionKey, explication.descriptionValues)}</p>
    </>
  );
}

const ATTENDU: Record<Locale, { titre: string; description: string }> = {
  fr: { titre: "Question refusée par le backend", description: "La question est trop longue (maximum 2000 caractères)." },
  en: { titre: "Question rejected by the backend", description: "The question is too long (maximum 2000 characters)." },
  de: { titre: "Frage vom Backend abgelehnt", description: "Die Frage ist zu lang (maximal 2000 Zeichen)." },
};

describe("Erreur proxy 'question_too_long' affichée traduite (pas le message brut)", () => {
  for (const locale of ["fr", "en", "de"] as const) {
    it(`locale='${locale}'`, () => {
      renderAvecIntl(<ErreurRendue status={400} code="question_too_long" values={{ max: 2000 }} />, { locale });

      expect(screen.getByTestId("titre")).toHaveTextContent(ATTENDU[locale].titre);
      expect(screen.getByTestId("description")).toHaveTextContent(ATTENDU[locale].description);
      // Le message interne français n'est JAMAIS affiché quand un code est présent.
      expect(screen.queryByText(/message interne français/)).not.toBeInTheDocument();
    });
  }
});

describe("Erreur proxy 'backend_unreachable' affichée traduite", () => {
  for (const locale of ["fr", "en", "de"] as const) {
    it(`locale='${locale}' n'affiche jamais le message brut français`, () => {
      renderAvecIntl(<ErreurRendue status={503} code="backend_unreachable" />, { locale });
      expect(screen.queryByText(/message interne français/)).not.toBeInTheDocument();
    });
  }
});
