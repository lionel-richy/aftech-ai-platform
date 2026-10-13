import { FileText } from "lucide-react";

import type { SourceItem } from "@/lib/types";

export function SourceCard({ source, afficherScore }: { source: SourceItem; afficherScore: boolean }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
          <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate" title={source.fichier}>
            {source.fichier}
          </span>
        </div>
        <span className="shrink-0 text-xs text-[var(--text-muted)]">page {source.page}</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{source.extrait}</p>
      {afficherScore && (
        <p className="mt-2 text-xs text-[var(--text-muted)]">score sémantique : {source.score.toFixed(3)}</p>
      )}
    </div>
  );
}
