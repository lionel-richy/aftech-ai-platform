import { Topbar } from "@/components/layout/Topbar";
import { Card, DemoBadge } from "@/components/ui/Card";
import { DemoBanner } from "@/components/administration/DemoBanner";

// Données FICTIVES, pour prévisualiser l'écran avant que le vrai système
// multi-tenant existe. Jamais présentées comme réelles (voir DemoBadge).
const UTILISATEURS_DEMO = [
  { nom: "A. Dubois", role: "Administrateur organisation", statut: "Actif" },
  { nom: "M. Nguyen", role: "Responsable IA", statut: "Actif" },
  { nom: "S. Okafor", role: "Utilisateur", statut: "Actif" },
  { nom: "J. Moreau", role: "Auditeur", statut: "Invité" },
];

const ROLES_PREPARES = [
  { nom: "Administrateur organisation", description: "Gère les utilisateurs, les intégrations et la facturation." },
  { nom: "Responsable IA", description: "Configure les modèles autorisés et les politiques d'accès." },
  { nom: "Utilisateur", description: "Utilise l'Assistant IA et consulte la Bibliothèque." },
  { nom: "Auditeur", description: "Lecture seule sur le journal d'audit et les métriques." },
];

const MODELES_AUTORISES_DEMO = [
  { nom: "Qwen/Qwen3-4B-Instruct-2507", usage: "Génération (actif)" },
  { nom: "BAAI/bge-m3", usage: "Embeddings (actif)" },
];

const JOURNAL_AUDIT_DEMO = [
  { date: "2026-10-03 09:14", evenement: "Connexion (démo)", acteur: "A. Dubois" },
  { date: "2026-10-02 17:40", evenement: "Consultation Bibliothèque", acteur: "S. Okafor" },
  { date: "2026-10-01 11:02", evenement: "Question posée à l'Assistant IA", acteur: "M. Nguyen" },
];

export default function AdministrationPage() {
  return (
    <>
      <Topbar title="Administration" description="Organisation, utilisateurs, rôles et politiques." />
      <main className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <DemoBanner />

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Organisation courante</h2>
            <DemoBadge />
          </div>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">AFTECH (organisation unique, démonstration)</p>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Utilisateurs</h2>
            <DemoBadge />
          </div>
          <table className="mt-3 w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th className="pb-2">Nom</th>
                <th className="pb-2">Rôle</th>
                <th className="pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              {UTILISATEURS_DEMO.map((u) => (
                <tr key={u.nom} className="border-t border-[var(--border)] text-[var(--text-secondary)]">
                  <td className="py-2 text-[var(--text-primary)]">{u.nom}</td>
                  <td className="py-2">{u.role}</td>
                  <td className="py-2">{u.statut}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Rôles préparés</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {ROLES_PREPARES.map((r) => (
              <div key={r.nom} className="rounded-[var(--radius-md)] border border-[var(--border)] p-3">
                <p className="text-sm font-medium text-[var(--text-primary)]">{r.nom}</p>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{r.description}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Modèles autorisés</h2>
            <span className="text-xs text-[var(--text-muted)]">Données réelles (depuis /health)</span>
          </div>
          <ul className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
            {MODELES_AUTORISES_DEMO.map((m) => (
              <li key={m.nom} className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border)] px-3 py-2">
                <span className="text-[var(--text-primary)]">{m.nom}</span>
                <span className="text-xs">{m.usage}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Politiques d&apos;accès</h2>
            <DemoBadge label="Prévisualisation" />
          </div>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Aucune politique d&apos;accès réelle n&apos;est encore appliquée. Cet espace est préparé pour la future
            authentification entreprise (voir docs/KNOWN_LIMITATIONS.md).
          </p>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Journal d&apos;audit</h2>
            <DemoBadge />
          </div>
          <ul className="mt-3 space-y-2 text-sm">
            {JOURNAL_AUDIT_DEMO.map((entree, i) => (
              <li key={i} className="flex items-center justify-between border-t border-[var(--border)] py-2 first:border-t-0">
                <span className="text-[var(--text-secondary)]">{entree.evenement}</span>
                <span className="text-xs text-[var(--text-muted)]">
                  {entree.acteur} · {entree.date}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </main>
    </>
  );
}
