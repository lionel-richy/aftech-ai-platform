import { Database, Folder, GitBranch, GitFork, HardDrive, KanbanSquare } from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";

// Toutes "Non connecté" pour cette Demo V1 — aucun faux connecteur fonctionnel.
// Icônes génériques (lucide-react n'inclut plus les logos de marque).
const INTEGRATIONS = [
  { nom: "Jira Cloud", icone: KanbanSquare, note: "Première intégration réelle prévue après la Demo V1." },
  { nom: "SharePoint", icone: HardDrive },
  { nom: "OneDrive", icone: HardDrive },
  { nom: "Google Drive", icone: HardDrive },
  { nom: "Dossiers locaux / NAS", icone: Folder },
  { nom: "GitHub", icone: GitFork },
  { nom: "GitLab", icone: GitBranch },
  { nom: "Bases de données", icone: Database },
] as const;

export default function IntegrationsPage() {
  return (
    <>
      <Topbar title="Intégrations" description="Aucun connecteur n'est encore actif dans cette version." />
      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATIONS.map((integration) => (
            <IntegrationCard
              key={integration.nom}
              nom={integration.nom}
              icone={<integration.icone aria-hidden className="h-5 w-5 text-[var(--text-secondary)]" />}
              etat="non_connecte"
              note={"note" in integration ? integration.note : undefined}
            />
          ))}
        </div>
      </main>
    </>
  );
}
