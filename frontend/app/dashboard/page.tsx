import { AlertCircle, Timer } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { BackendUnavailableState } from "@/components/ui/StateViews";
import { GpuBenchmarkSection } from "@/components/dashboard/GpuBenchmarkSection";
import { GpuHealthCheck } from "@/components/dashboard/GpuHealthCheck";
import { InstrumentationPlaceholders } from "@/components/dashboard/InstrumentationPlaceholders";
import { StatusBreakdownChart } from "@/components/dashboard/StatusBreakdownChart";
import { appelerBackend } from "@/lib/backend";
import { lireComparisonGpu } from "@/lib/gpuBenchmark";
import { LOCALE_BCP47, type Locale } from "@/i18n/config";
import type { MetricsResponse } from "@/lib/types";

// Données réelles à chaque requête (CSV de benchmark peut changer) : jamais
// prérendu statiquement au build. Équivalent, sous Cache Components, de
// l'ancien "export const dynamic = 'force-dynamic'".
//
// IMPORTANT : cette page n'appelle PLUS /health au chargement — exigence
// "la vérification GPU détaillée doit être lancée uniquement lors d'une
// vraie question, ou manuellement" (voir GpuHealthCheck.tsx, déclenché par
// un clic). /metrics reste auto-chargée : ce sont des compteurs opérationnels
// déjà accumulés côté backend, pas un déclenchement de calcul GPU.
export const instant = false;

export default async function DashboardPage() {
  const [metriques, comparaisonGpu, locale, tNav, t] = await Promise.all([
    appelerBackend<MetricsResponse>("/metrics"),
    lireComparisonGpu(),
    getLocale(),
    getTranslations("Nav"),
    getTranslations("Dashboard"),
  ]);

  const nombres = new Intl.NumberFormat(LOCALE_BCP47[locale as Locale]);
  const m = metriques.ok ? metriques.data : null;

  return (
    <>
      <Topbar title={tNav("dashboard")} description={t("topbarDescription")} />
      <main className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("gpuCheckTitle")}</h2>
          <div className="mt-3">
            <GpuHealthCheck />
          </div>
        </Card>

        {m && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label={t("statLatency")}
              value={m.latence_moyenne_secondes != null ? `${m.latence_moyenne_secondes.toFixed(2)} s` : null}
              unavailableReason={m.latence_moyenne_secondes == null ? t("statLatencyUnavailable") : undefined}
              icon={<Timer className="h-4 w-4" aria-hidden />}
            />
            <StatTile label={t("statRequestsTotal")} value={nombres.format(m.requests_total)} />
            <StatTile
              label={t("statErrorsTotal")}
              value={nombres.format(m.errors_total)}
              icon={<AlertCircle className="h-4 w-4" aria-hidden />}
            />
          </div>
        )}

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("statusBreakdownTitle")}</h2>
          <div className="mt-3">{m ? <StatusBreakdownChart metrics={m} /> : <BackendUnavailableState />}</div>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("gpuComparisonTitle")}</h2>
          <div className="mt-3">
            <GpuBenchmarkSection comparaison={comparaisonGpu} />
          </div>
        </Card>

        <div>
          <h2 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">{t("instrumentationTitle")}</h2>
          <InstrumentationPlaceholders />
        </div>
      </main>
    </>
  );
}
