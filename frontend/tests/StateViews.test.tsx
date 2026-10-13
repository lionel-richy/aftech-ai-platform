import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BackendUnavailableState, EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { renderAvecIntl } from "./test-utils";

describe("États partagés (loading / vide / erreur / backend indisponible)", () => {
  it("LoadingState affiche un message de chargement", () => {
    renderAvecIntl(<LoadingState label="Chargement du tableau de bord…" />);
    expect(screen.getByText("Chargement du tableau de bord…")).toBeInTheDocument();
  });

  it("LoadingState affiche le libellé par défaut traduit si aucun n'est fourni", () => {
    renderAvecIntl(<LoadingState />, { locale: "en" });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("EmptyState affiche le titre et la description", () => {
    renderAvecIntl(<EmptyState title="Aucun document" description="Rien à afficher." />);
    expect(screen.getByText("Aucun document")).toBeInTheDocument();
    expect(screen.getByText("Rien à afficher.")).toBeInTheDocument();
  });

  it("ErrorState affiche le titre d'erreur", () => {
    renderAvecIntl(<ErrorState title="Erreur de chargement" />);
    expect(screen.getByText("Erreur de chargement")).toBeInTheDocument();
  });

  it("BackendUnavailableState affiche le libellé standard", () => {
    renderAvecIntl(<BackendUnavailableState />);
    expect(screen.getByText("Backend indisponible")).toBeInTheDocument();
  });

  it("BackendUnavailableState affiche une description personnalisée si fournie", () => {
    renderAvecIntl(<BackendUnavailableState description="Aucun GPU CUDA détecté." />);
    expect(screen.getByText("Aucun GPU CUDA détecté.")).toBeInTheDocument();
  });

  it("BackendUnavailableState affiche le libellé standard en allemand", () => {
    renderAvecIntl(<BackendUnavailableState />, { locale: "de" });
    expect(screen.getByText("Backend nicht verfügbar")).toBeInTheDocument();
  });
});
