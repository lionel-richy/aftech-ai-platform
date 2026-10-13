import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BackendUnavailableState, EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";

describe("États partagés (loading / vide / erreur / backend indisponible)", () => {
  it("LoadingState affiche un message de chargement", () => {
    render(<LoadingState label="Chargement du tableau de bord…" />);
    expect(screen.getByText("Chargement du tableau de bord…")).toBeInTheDocument();
  });

  it("EmptyState affiche le titre et la description", () => {
    render(<EmptyState title="Aucun document" description="Rien à afficher." />);
    expect(screen.getByText("Aucun document")).toBeInTheDocument();
    expect(screen.getByText("Rien à afficher.")).toBeInTheDocument();
  });

  it("ErrorState affiche le titre d'erreur", () => {
    render(<ErrorState title="Erreur de chargement" />);
    expect(screen.getByText("Erreur de chargement")).toBeInTheDocument();
  });

  it("BackendUnavailableState affiche le libellé standard", () => {
    render(<BackendUnavailableState />);
    expect(screen.getByText("Backend indisponible")).toBeInTheDocument();
  });

  it("BackendUnavailableState affiche une description personnalisée si fournie", () => {
    render(<BackendUnavailableState description="Aucun GPU CUDA détecté." />);
    expect(screen.getByText("Aucun GPU CUDA détecté.")).toBeInTheDocument();
  });
});
