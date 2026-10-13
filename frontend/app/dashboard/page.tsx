import { Activity, AlertCircle, Cpu, Database, FileStack, Gauge, Layers, Sparkles, Timer } from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { BackendUnavailableState } from "@/components/ui/StateViews";
import { GpuBenchmarkSection } from "@/components/dashboard/GpuBenchmarkSection";
import { InstrumentationPlaceholders } from "@/components/dashboard/InstrumentationPlaceholders";
import { StatusBreakdownChart } from "@/components/dashboard/StatusBreakdownChart";
import { appelerBackend } from "@/lib/backend";
import { lireComparisonGpu } from "@/lib/gpuBenchmark";
import type { HealthResponse, MetricsResponse } from "@/lib/types";

// Données réelles à chaque requête (backend/CSV peuvent changer) : jamais
// prérendu statiquement au build. Équivalent, sous Cache Components, de
// l'ancien "export const dynamic = 'force-dynamic'".
export const instant = false;

function formaterGo(octets: number): string {
  return (octets / 1024 ** 3).toFixed(2);
}

export default async function DashboardPage() {
  const [sante, metriques, comparaisonGpu] = await Promise.all([
    appelerBackend<HealthResponse>("/health", { authentifie: false }),
    appelerBackend<MetricsResponse>("/metrics"),
    lireComparisonGpu(),
  ]);

  if (!sante.ok) {
    return (
      <>
        <Topbar title="Tableau de bord" />
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
      <Topbar title="Tableau de bord" description="Uniquement des métriques réellement mesurées." />
      <main className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Backend"
            value={h.ready ? "Opérationnel" : "Dégradé"}
            icon={<Activity className="h-4 w-4" aria-hidden />}
          />
          <StatTile label="Documents" value={h.documents_count} icon={<FileStack className="h-4 w-4" aria-hidden />} />
          <StatTile label="Passages indexés" value={h.chunks_count} icon={<Layers className="h-4 w-4" aria-hidden />} />
          <StatTile label="GPU actif" value={h.gpu} icon={<Cpu className="h-4 w-4" aria-hidden />} />
          <StatTile label="Modèle LLM" value={h.llm_model} icon={<Sparkles className="h-4 w-4" aria-hidden />} />
          <StatTile label="Modèle d'embeddings" value={h.embedding_model} icon={<Database className="h-4 w-4" aria-hidden />} />
          <StatTile
            label="Mémoire GPU"
            value={
              h.vram_utilisee_octets != null && h.vram_totale_octets != null
                ? `${formaterGo(h.vram_utilisee_octets)} / ${formaterGo(h.vram_totale_octets)} Go`
                : null
            }
            unavailableReason={
              h.vram_totale_octets == null ? "Aucun GPU actif (mode dégradé)." : undefined
            }
            icon={<Gauge className="h-4 w-4" aria-hidden />}
          />
          <StatTile
            label="Latence moyenne"
            value={m?.latence_moyenne_secondes != null ? `${m.latence_moyenne_secondes.toFixed(2)} s` : null}
            unavailableReason={m?.latence_moyenne_secondes == null ? "Aucune requête mesurée pour l'instant." : undefined}
            icon={<Timer className="h-4 w-4" aria-hidden />}
          />
        </div>

        {m && (
          <div className="grid gap-4 sm:grid-cols-2">
            <StatTile label="Requêtes depuis le démarrage" value={m.requests_total} />
            <StatTile label="Erreurs depuis le démarrage" value={m.errors_total} icon={<AlertCircle className="h-4 w-4" aria-hidden />} />
          </div>
        )}

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Répartition des statuts</h2>
          <div className="mt-3">{m ? <StatusBreakdownChart metrics={m} /> : <BackendUnavailableState />}</div>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Comparaison GPU (T4 / L4 / A100)</h2>
          <div className="mt-3">
            <GpuBenchmarkSection comparaison={comparaisonGpu} />
          </div>
        </Card>

        <div>
          <h2 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Métriques à venir</h2>
          <InstrumentationPlaceholders />
        </div>
      </main>
    </>
  );
}
