"use client";

import { useTranslations } from "next-intl";

const CLES = [
  "instrumentationGpuConsumption",
  "instrumentationCost",
  "instrumentationQuality",
  "instrumentationHallucinations",
  "instrumentationAvailability",
] as const;

// Emplacements préparés visuellement pour des métriques pas encore
// instrumentées — jamais remplis d'un chiffre inventé.
export function InstrumentationPlaceholders() {
  const t = useTranslations("Dashboard");

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {CLES.map((cle) => (
        <div
          key={cle}
          className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-4 text-center"
        >
          <p className="text-sm font-medium text-[var(--text-secondary)]">{t(cle)}</p>
          <p className="mt-2 text-xs text-[var(--text-muted)]">{t("instrumentationToInstrument")}</p>
        </div>
      ))}
    </div>
  );
}
