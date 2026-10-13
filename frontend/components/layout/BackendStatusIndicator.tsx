"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useEtatMoteur } from "@/lib/engineStatus";

// IMPORTANT : ce composant tourne en PERMANENCE (toutes les pages, toutes les
// 30 s, tant que l'onglet est ouvert). Il n'appelle JAMAIS /api/health ni
// /api/ask (routes GPU) — seulement /api/availability (CPU uniquement,
// fonction Modal séparée, voir backend/app/modal_app.py). Sinon, ce ping
// automatique empêcherait indéfiniment le scale-to-zero du GPU (c'est le bug
// corrigé ici). L'état détaillé du MOTEUR (démarrage/prêt/indisponible) vient
// uniquement de vraies interactions (lib/engineStatus.ts), jamais de ce ping.
type EtatApi = "verification" | "disponible" | "indisponible";

export function BackendStatusIndicator({ compact = false }: { compact?: boolean }) {
  const [etatApi, setEtatApi] = useState<EtatApi>("verification");
  const etatMoteur = useEtatMoteur();
  const t = useTranslations("BackendStatus");

  useEffect(() => {
    let annule = false;

    async function verifier() {
      try {
        const reponse = await fetch("/api/availability", { cache: "no-store" });
        if (!annule) setEtatApi(reponse.ok ? "disponible" : "indisponible");
      } catch {
        if (!annule) setEtatApi("indisponible");
      }
    }

    verifier();
    const intervalle = setInterval(verifier, 30000);
    return () => {
      annule = true;
      clearInterval(intervalle);
    };
  }, []);

  const { couleur, label } = (() => {
    if (etatApi === "verification") return { couleur: "bg-[var(--text-muted)]", label: t("checking") };
    if (etatApi === "indisponible") return { couleur: "bg-danger", label: t("apiUnreachable") };

    // API disponible : le détail affiché dépend de l'état du MOTEUR, connu
    // uniquement via de vraies interactions (jamais ce ping automatique).
    switch (etatMoteur.etat) {
      case "demarrage":
        return { couleur: "bg-warning", label: t("engineStarting") };
      case "pret":
        return { couleur: "bg-success", label: t("engineReady") };
      case "indisponible":
        return { couleur: "bg-danger", label: t("engineUnavailable") };
      case "veille":
      default:
        return { couleur: "bg-[var(--text-muted)]", label: t("engineIdle") };
    }
  })();

  return (
    <div
      role="status"
      aria-label={label}
      title={label}
      className="flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1.5 text-xs text-[var(--text-secondary)]"
    >
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${couleur}`} />
      {!compact && <span>{label}</span>}
    </div>
  );
}
