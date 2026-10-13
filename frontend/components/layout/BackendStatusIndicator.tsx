"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { HealthResponse } from "@/lib/types";

type Etat = "chargement" | "ok" | "degrade" | "inaccessible";

export function BackendStatusIndicator({ compact = false }: { compact?: boolean }) {
  const [etat, setEtat] = useState<Etat>("chargement");
  const t = useTranslations("BackendStatus");

  useEffect(() => {
    let annule = false;

    async function verifier() {
      try {
        const reponse = await fetch("/api/health", { cache: "no-store" });
        if (!reponse.ok) {
          if (!annule) setEtat("inaccessible");
          return;
        }
        const donnees: HealthResponse = await reponse.json();
        if (!annule) setEtat(donnees.ready ? "ok" : "degrade");
      } catch {
        if (!annule) setEtat("inaccessible");
      }
    }

    verifier();
    const intervalle = setInterval(verifier, 30000);
    return () => {
      annule = true;
      clearInterval(intervalle);
    };
  }, []);

  const STYLES: Record<Etat, { couleur: string; label: string }> = {
    chargement: { couleur: "bg-[var(--text-muted)]", label: t("checking") },
    ok: { couleur: "bg-success", label: t("ok") },
    degrade: { couleur: "bg-warning", label: t("degraded") },
    inaccessible: { couleur: "bg-danger", label: t("unreachable") },
  };

  const { couleur, label } = STYLES[etat];

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
