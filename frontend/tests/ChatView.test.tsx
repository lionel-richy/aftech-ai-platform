import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/components/assistant/ChatView";
import { etatMoteurActuel, reinitialiserEtatMoteurPourLesTests } from "@/lib/engineStatus";
import { renderAvecIntl } from "./test-utils";

const REPONSE_OK = {
  answer: "Azure propose du stockage. [source : doc.pdf, page 1]",
  status: "COMPLETE",
  sources: [],
  validated_claims: [],
  timings: { recherche_secondes: 0.1, generation_secondes: 1.0, total_secondes: 1.1 },
  request_id: "req-1",
};

// Exigence Partie 2 : contrairement à la surveillance automatique (jamais de
// route GPU), une VRAIE question doit continuer à démarrer le moteur
// normalement — /api/ask (route GPU) est bien appelée, et l'état partagé du
// moteur passe par "demarrage" puis "pret".
describe("ChatView — une vraie question continue de démarrer le moteur", () => {
  beforeEach(() => {
    reinitialiserEtatMoteurPourLesTests();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("envoie bien la question à /api/ask et publie l'état 'pret' après succès", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(REPONSE_OK), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<ChatView />);

    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Quel document parle d'Azure ?" } });
    fireEvent.click(screen.getByLabelText("Envoyer la question"));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ask",
      expect.objectContaining({ method: "POST" }),
    );
    // La route appelée EST bien une route GPU (comportement normal et
    // attendu pour une vraie question — à ne jamais confondre avec le
    // ping automatique de BackendStatusIndicator).
    expect(fetchMock.mock.calls[0][0]).toBe("/api/ask");

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("pret"));
  });

  it("publie l'état 'indisponible' si le backend ne répond pas", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    renderAvecIntl(<ChatView />);

    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Une question ?" } });
    fireEvent.click(screen.getByLabelText("Envoyer la question"));

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("indisponible"));
  });

  it("passe par l'état 'demarrage' pendant que la requête est en cours", async () => {
    let resoudre: (v: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resoudre = resolve;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<ChatView />);
    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Une question ?" } });

    act(() => {
      fireEvent.click(screen.getByLabelText("Envoyer la question"));
    });

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("demarrage"));

    await act(async () => {
      resoudre(new Response(JSON.stringify(REPONSE_OK), { status: 200 }));
      await Promise.resolve();
    });
  });
});
