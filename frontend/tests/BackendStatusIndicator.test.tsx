import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BackendStatusIndicator } from "@/components/layout/BackendStatusIndicator";
import { definirEtatMoteur, reinitialiserEtatMoteurPourLesTests } from "@/lib/engineStatus";
import { renderAvecIntl } from "./test-utils";

// Exigence centrale de la Partie 2 : la surveillance AUTOMATIQUE (ce
// composant, monté sur toutes les pages) ne doit JAMAIS appeler une route
// GPU (/api/health, /api/ask) — seulement /api/availability (CPU, fonction
// Modal séparée). Sinon, Modal ne redescend jamais à zéro après
// scaledown_window=300 (bug réel corrigé ici).
describe("BackendStatusIndicator — n'appelle jamais une route GPU", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    reinitialiserEtatMoteurPourLesTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("appelle UNIQUEMENT /api/availability au montage, jamais /api/health ni /api/ask", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/availability", expect.anything());
    expect(fetchMock).not.toHaveBeenCalledWith("/api/health", expect.anything());
    expect(fetchMock).not.toHaveBeenCalledWith("/api/ask", expect.anything());

    vi.unstubAllGlobals();
  });

  it("ne maintient AUCUNE boucle vers une route GPU, même après de nombreux cycles de 30 s", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    // Simule 2 heures d'onglet ouvert (240 cycles de 30 s) : exactement le
    // scénario qui, avant correction, empêchait indéfiniment le scale-to-zero.
    for (let i = 0; i < 240; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(30000);
        await Promise.resolve();
      });
    }

    expect(fetchMock.mock.calls.length).toBeGreaterThan(1);
    for (const appel of fetchMock.mock.calls) {
      expect(appel[0]).toBe("/api/availability");
    }

    vi.unstubAllGlobals();
  });

  it("l'état détaillé du moteur (démarrage/prêt/indisponible) ne change JAMAIS tout seul : seule une vraie interaction le fait", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    // Sans aucune vraie question ni vérification manuelle : l'API est
    // disponible, mais le moteur reste en VEILLE indéfiniment.
    for (let i = 0; i < 10; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(30000);
        await Promise.resolve();
      });
    }
    expect(screen.getByRole("status")).toHaveAttribute("title", expect.stringContaining("veille"));

    // Une VRAIE interaction (simulée ici directement, comme le ferait
    // ChatView après une vraie question) change bien l'affichage.
    await act(async () => {
      definirEtatMoteur({ etat: "pret", vramUtiliseeOctets: 1_000_000, vramTotaleOctets: 2_000_000 });
    });
    expect(screen.getByRole("status")).toHaveAttribute("title", expect.stringContaining("prêt"));

    vi.unstubAllGlobals();
  });
});
