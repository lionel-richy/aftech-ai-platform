import { FlaskConical } from "lucide-react";

export function DemoBanner() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-accent/30 bg-accent/10 p-4"
    >
      <FlaskConical aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
      <div>
        <p className="text-sm font-semibold text-accent">Mode démonstration</p>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Toutes les données de cet espace (utilisateurs, rôles, journal d&apos;audit) sont fictives. Aucune
          authentification multi-organisation réelle n&apos;est active, et aucune action ci-dessous n&apos;a d&apos;effet réel.
        </p>
      </div>
    </div>
  );
}
