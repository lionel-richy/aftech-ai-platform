import type { AnswerStatus } from "@/lib/types";

const STYLES: Record<AnswerStatus, string> = {
  COMPLETE: "text-success bg-[var(--success-bg)] border-success/30",
  PARTIAL: "text-warning bg-[var(--warning-bg)] border-warning/30",
  NOT_FOUND: "text-danger bg-[var(--danger-bg)] border-danger/30",
};

const LABELS: Record<AnswerStatus, string> = {
  COMPLETE: "Complet",
  PARTIAL: "Partiel",
  NOT_FOUND: "Non trouvé",
};

export function StatusBadge({ status }: { status: AnswerStatus }) {
  return (
    <span
      role="status"
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${STYLES[status]}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {LABELS[status]} <span className="text-[10px] opacity-70">({status})</span>
    </span>
  );
}
