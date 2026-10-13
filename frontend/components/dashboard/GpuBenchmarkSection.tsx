import { EmptyState } from "@/components/ui/StateViews";
import type { ComparisonGpu } from "@/lib/gpuBenchmark";

export function GpuBenchmarkSection({ comparaison }: { comparaison: ComparisonGpu }) {
  if (!comparaison.executed) {
    return (
      <EmptyState
        title="Benchmark non exécuté"
        description="Lancez ./scripts/run_gpu_benchmark.sh <T4|L4|A100> puis scripts/build_gpu_comparison.py pour remplir cette section."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            <th className="pb-2 pr-4">GPU</th>
            <th className="pb-2 pr-4">VRAM</th>
            <th className="pb-2 pr-4">Latence moy.</th>
            <th className="pb-2 pr-4">Tokens/s</th>
            <th className="pb-2 pr-4">Pic mémoire</th>
            <th className="pb-2">Erreurs</th>
          </tr>
        </thead>
        <tbody>
          {comparaison.lignes.map((ligne) => (
            <tr key={ligne.gpu} className="border-t border-[var(--border)] text-[var(--text-primary)]">
              <td className="py-2 pr-4 font-medium">{ligne.gpu}</td>
              <td className="py-2 pr-4">{ligne.vram_totale_go ?? "—"} Go</td>
              <td className="py-2 pr-4">{ligne.temps_total_moyen_s?.toFixed(2) ?? "—"} s</td>
              <td className="py-2 pr-4">{ligne.tokens_par_seconde_moyen?.toFixed(1) ?? "—"}</td>
              <td className="py-2 pr-4">{ligne.memoire_gpu_pic_go_max ?? "—"} Go</td>
              <td className="py-2">{ligne.nb_erreurs ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-[var(--text-muted)]">
        Recommandation détaillée par cas d&apos;usage : voir results/benchmarks/gpu/recommendation.md
      </p>
    </div>
  );
}
