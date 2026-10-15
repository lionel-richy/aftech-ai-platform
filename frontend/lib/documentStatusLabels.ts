import type { DocumentStatus } from "./types";

// Partagé entre DocumentCard.tsx (badge sur la liste) et
// AjouterDocumentButton.tsx (progression pendant l'upload) — namespace
// "Bibliotheque" dans messages/{locale}.json.
export const CLE_STATUT: Record<
  Exclude<DocumentStatus, "READY">,
  "statusUploaded" | "statusExtracting" | "statusIndexing" | "statusFailed" | "statusDeleting"
> = {
  UPLOADED: "statusUploaded",
  EXTRACTING: "statusExtracting",
  INDEXING: "statusIndexing",
  FAILED: "statusFailed",
  DELETING: "statusDeleting",
};
