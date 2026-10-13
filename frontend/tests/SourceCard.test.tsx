import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceCard } from "@/components/assistant/SourceCard";
import type { SourceItem } from "@/lib/types";
import { renderAvecIntl } from "./test-utils";

const SOURCE: SourceItem = {
  fichier: "politique_securite.txt",
  page: 1,
  extrait: "Les mots de passe doivent contenir au moins 14 caractères.",
  score: 0.912,
};

describe("SourceCard", () => {
  it("affiche le fichier, la page et l'extrait", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.getByText("politique_securite.txt")).toBeInTheDocument();
    expect(screen.getByText("page 1")).toBeInTheDocument();
    expect(screen.getByText(SOURCE.extrait)).toBeInTheDocument();
  });

  it("masque le score par défaut (visible seulement en détails techniques)", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.queryByText(/score sémantique/)).not.toBeInTheDocument();
  });

  it("affiche le score quand demandé", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore />);
    expect(screen.getByText(/score sémantique : 0.912/)).toBeInTheDocument();
  });

  it("garde le fichier et l'extrait dans leur langue d'origine même en anglais", () => {
    // Exigence : les citations/extraits exacts ne sont JAMAIS traduits, quelle
    // que soit la langue de l'interface.
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />, { locale: "en" });
    expect(screen.getByText("politique_securite.txt")).toBeInTheDocument();
    expect(screen.getByText(SOURCE.extrait)).toBeInTheDocument();
    // Seul le libellé structurel ("page") est traduit.
    expect(screen.getByText("page 1")).toBeInTheDocument();
  });
});
