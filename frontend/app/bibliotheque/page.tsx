import { Topbar } from "@/components/layout/Topbar";
import { BackendUnavailableState, ErrorState, EmptyState } from "@/components/ui/StateViews";
import { BibliothequeView } from "@/components/bibliotheque/BibliothequeView";
import { appelerBackend } from "@/lib/backend";
import type { DocumentItem } from "@/lib/types";

// Données réelles à chaque requête (backend) : jamais prérendu statiquement.
export const instant = false;

export default async function BibliothequePage() {
  const resultat = await appelerBackend<DocumentItem[]>("/documents");

  return (
    <>
      <Topbar title="Bibliothèque" description="Documents réellement indexés par le backend." />
      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        {!resultat.ok && resultat.status === 503 && (
          <BackendUnavailableState description={resultat.message} />
        )}
        {!resultat.ok && resultat.status !== 503 && (
          <ErrorState title="Impossible de charger les documents" description={resultat.message} />
        )}
        {resultat.ok && resultat.data.length === 0 && (
          <EmptyState title="Aucun document indexé" description="L'index ne contient aucun document pour le moment." />
        )}
        {resultat.ok && resultat.data.length > 0 && <BibliothequeView documents={resultat.data} />}
      </main>
    </>
  );
}
