"use client";

import { Building2 } from "lucide-react";
import { useTranslations } from "next-intl";

// Préparé pour le futur multi-tenant : une seule organisation existe pour
// l'instant, le sélecteur est donc désactivé plutôt que de simuler un choix
// qui n'existe pas réellement.
export function OrganizationSwitcher() {
  const t = useTranslations("OrganizationSwitcher");

  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      title={t("tooltip")}
      className="flex w-full items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border)] px-2.5 py-2 text-left text-xs text-[var(--text-secondary)] opacity-70"
    >
      <Building2 aria-hidden className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{t("label")}</span>
    </button>
  );
}
