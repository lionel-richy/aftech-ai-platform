import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceCard } from "@/components/assistant/SourceCard";
import type { SourceItem } from "@/lib/types";

const SOURCE: SourceItem = {
  fichier: "politique_securite.txt",
  page: 1,
  extrait: "Les mots de passe doivent contenir au moins 14 caractères.",
  score: 0.912,
};

describe("SourceCard", () => {
  it("affiche le fichier, la page et l'extrait", () => {
    render(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.getByText("politique_securite.txt")).toBeInTheDocument();
    expect(screen.getByText("page 1")).toBeInTheDocument();
    expect(screen.getByText(SOURCE.extrait)).toBeInTheDocument();
  });

  it("masque le score par défaut (visible seulement en détails techniques)", () => {
    render(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.queryByText(/score sémantique/)).not.toBeInTheDocument();
  });

  it("affiche le score quand demandé", () => {
    render(<SourceCard source={SOURCE} afficherScore />);
    expect(screen.getByText(/score sémantique : 0.912/)).toBeInTheDocument();
  });
});
