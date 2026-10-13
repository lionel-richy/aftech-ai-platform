"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";

// Pas d'upload public à cette étape : le bouton explique plutôt que de
// simuler une fonctionnalité qui n'existe pas encore.
export function AjouterDocumentButton() {
  const [ouvert, setOuvert] = useState(false);
  const t = useTranslations("Bibliotheque");

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        aria-expanded={ouvert}
        className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        <Plus aria-hidden className="h-3.5 w-3.5" />
        {t("addDocument")}
      </button>
      {ouvert && (
        <div
          role="status"
          className="absolute right-0 top-full z-10 mt-2 w-64 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)] shadow-lg"
        >
          {t("addDocumentNote")}
        </div>
      )}
    </div>
  );
}
