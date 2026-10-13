import { Activity, AlertCircle, Cpu, Database, FileStack, Gauge, Layers, Sparkles, Timer } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { BackendUnavailableState } from "@/components/ui/StateViews";
import { GpuBenchmarkSection } from "@/components/dashboard/GpuBenchmarkSection";
import { InstrumentationPlaceholders } from "@/components/dashboard/InstrumentationPlaceholders";
import { StatusBreakdownChart } from "@/components/dashboard/StatusBreakdownChart";
import { appelerBackend } from "@/lib/backend";
import { lireComparisonGpu } from "@/lib/gpuBenchmark";
import { LOCALE_BCP47, type Locale } from "@/i18n/config";
import type { HealthResponse, MetricsResponse } from "@/lib/types";

// Données réelles à chaque requête (backend/CSV peuvent changer) : jamais
// prérendu statiquement au build. Équivalent, sous Cache Components, de
// l'ancien "export const dynamic = 'force-dynamic'".
export const instant = false;

function formaterGo(octets: number): string {
  return (octets / 1024 ** 3).toFixed(2);
}

export default async function DashboardPage() {
  const [sante, metriques, comparaisonGpu, locale, tNav, t] = await Promise.all([
    appelerBackend<HealthResponse>("/health", { authentifie: false }),
    appelerBackend<MetricsResponse>("/metrics"),
    lireComparisonGpu(),
    getLocale(),
    getTranslations("Nav"),
    getTranslations("Dashboard"),
  ]);

  const nombres = new Intl.NumberFormat(LOCALE_BCP47[locale as Locale]);

  if (!sante.ok) {
    return (
      <>
        <Topbar title={tNav("dashboard")} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <BackendUnavailableState description={sante.message} />
        </main>
      </>
    );
  }

  const h = sante.data;
  const m = metriques.ok ? metriques.data : null;

  return (
    <>
      <Topbar title={tNav("dashboard")} description={t("topbarDescription")} />
      <main className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label={t("statBackend")}
            value={h.ready ? t("statOperational") : t("statDegraded")}
            icon={<Activity className="h-4 w-4" aria-hidden />}
          />
          <StatTile label={t("statDocuments")} value={nombres.format(h.documents_count)} icon={<FileStack className="h-4 w-4" aria-hidden />} />
          <StatTile label={t("statPassagesIndexed")} value={nombres.format(h.chunks_count)} icon={<Layers className="h-4 w-4" aria-hidden />} />
          <StatTile label={t("statGpuActive")} value={h.gpu} icon={<Cpu className="h-4 w-4" aria-hidden />} />
          <StatTile label={t("statLlmModel")} value={h.llm_model} icon={<Sparkles className="h-4 w-4" aria-hidden />} />
          <StatTile label={t("statEmbeddingModel")} value={h.embedding_model} icon={<Database className="h-4 w-4" aria-hidden />} />
          <StatTile
            label={t("statGpuMemory")}
            value={
              h.vram_utilisee_octets != null && h.vram_totale_octets != null
                ? `${formaterGo(h.vram_utilisee_octets)} / ${formaterGo(h.vram_totale_octets)} Go`
                : null
            }
            unavailableReason={h.vram_totale_octets == null ? t("statGpuMemoryUnavailable") : undefined}
            icon={<Gauge className="h-4 w-4" aria-hidden />}
          />
          <StatTile
            label={t("statLatency")}
            value={m?.latence_moyenne_secondes != null ? `${m.latence_moyenne_secondes.toFixed(2)} s` : null}
            unavailableReason={m?.latence_moyenne_secondes == null ? t("statLatencyUnavailable") : undefined}
            icon={<Timer className="h-4 w-4" aria-hidden />}
          />
        </div>

        {m && (
          <div className="grid gap-4 sm:grid-cols-2">
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
