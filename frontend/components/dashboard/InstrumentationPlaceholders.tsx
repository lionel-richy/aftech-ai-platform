const EMPLACEMENTS = [
  "Consommation GPU",
  "Coût estimé",
  "Qualité",
  "Hallucinations",
  "Disponibilité",
];

// Emplacements préparés visuellement pour des métriques pas encore
// instrumentées — jamais remplis d'un chiffre inventé.
export function InstrumentationPlaceholders() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {EMPLACEMENTS.map((nom) => (
        <div
          key={nom}
          className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-4 text-center"
        >
          <p className="text-sm font-medium text-[var(--text-secondary)]">{nom}</p>
          <p className="mt-2 text-xs text-[var(--text-muted)]">À instrumenter</p>
        </div>
      ))}
    </div>
  );
}
