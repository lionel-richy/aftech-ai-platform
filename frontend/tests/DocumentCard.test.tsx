import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentCard } from "@/components/bibliotheque/DocumentCard";
import type { DocumentItem } from "@/lib/types";
import { renderAvecIntl } from "./test-utils";

function construireDocument(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    nom_fichier: "rapport.pdf",
    pages: 10,
    passages: 20,
    hash_sha256: "abcdef0123456789",
    modele_embeddings: "BAAI/bge-m3",
    date_index: "2026-01-01T00:00:00Z",
    supprimable: false,
    ...overrides,
  };
}

describe("DocumentCard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("affiche 'Indexé' pour un document historique (non supprimable, pas de bouton supprimer)", () => {
    renderAvecIntl(<DocumentCard document={construireDocument()} />);
    expect(screen.getByText("Indexé")).toBeInTheDocument();
    expect(screen.queryByText("Supprimer")).not.toBeInTheDocument();
  });

  it("affiche le statut FAILED avec le message d'erreur", () => {
    renderAvecIntl(
      <DocumentCard
        document={construireDocument({
          id: "abc",
          statut: "FAILED",
          message_erreur: "Le fichier PDF est corrompu ou illisible.",
          supprimable: true,
        })}
      />,
    );
    expect(screen.getByText("Échec")).toBeInTheDocument();
    expect(screen.getByText("Le fichier PDF est corrompu ou illisible.")).toBeInTheDocument();
  });

  it("affiche le statut en anglais quand la locale est 'en'", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "a", statut: "INDEXING", supprimable: true })} />, {
      locale: "en",
    });
    expect(screen.getByText("Indexing…")).toBeInTheDocument();
  });

  it("affiche le statut en allemand quand la locale est 'de'", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "a", statut: "EXTRACTING", supprimable: true })} />, {
      locale: "de",
    });
    expect(screen.getByText("Text wird extrahiert…")).toBeInTheDocument();
  });

  it("le nom de fichier n'est JAMAIS traduit, quelle que soit la locale", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ nom_fichier: "Rapport_Confidentiel_2026.pdf" })} />, {
      locale: "de",
    });
    expect(screen.getByText("Rapport_Confidentiel_2026.pdf")).toBeInTheDocument();
  });

  it("un document supprimable affiche le bouton Supprimer, puis demande confirmation", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));

    expect(screen.getByText("Supprimer ce document ?")).toBeInTheDocument();
    expect(screen.getByText("Oui, supprimer")).toBeInTheDocument();
    expect(screen.getByText("Annuler")).toBeInTheDocument();
  });

  it("annuler referme la confirmation sans rien supprimer", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Annuler"));

    expect(screen.queryByText("Supprimer ce document ?")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirmer appelle DELETE /api/documents/{id} et notifie le parent au succès", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const onSupprime = vi.fn();
    renderAvecIntl(
      <DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} onSupprime={onSupprime} />,
    );

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Oui, supprimer"));

    await waitFor(() => expect(onSupprime).toHaveBeenCalledWith("abc"));
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/abc", { method: "DELETE" });
  });

  it("affiche une erreur si la suppression échoue, sans planter", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Oui, supprimer"));

    await waitFor(() => expect(screen.getByText("La suppression a échoué. Réessayez.")).toBeInTheDocument());
  });
});
