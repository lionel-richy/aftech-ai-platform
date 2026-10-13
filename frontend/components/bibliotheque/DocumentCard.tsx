"use client";

import { FileText, Layers } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { LOCALE_BCP47, type Locale } from "@/i18n/config";
import type { DocumentItem } from "@/lib/types";

export function DocumentCard({ document }: { document: DocumentItem }) {
  const locale = useLocale() as Locale;
  const t = useTranslations("Bibliotheque");

  const dateFormatee = document.date_index
    ? new Intl.DateTimeFormat(LOCALE_BCP47[locale], {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(new Date(document.date_index))
    : null;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-[var(--radius-md)] bg-primary/10 p-2 text-primary">
          <FileText aria-hidden className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]" title={document.nom_fichier}>
            {document.nom_fichier}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)]">
            <span className="inline-flex items-center gap-1">
              <Layers aria-hidden className="h-3 w-3" />
              {t("pagesPassages", { pages: document.pages, passages: document.passages })}
            </span>
            {dateFormatee && <span>{t("indexedOn", { date: dateFormatee })}</span>}
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-success/30 bg-[var(--success-bg)] px-2 py-0.5 text-[11px] font-medium text-success">
          {t("indexedBadge")}
        </span>
      </div>
      <p className="mt-3 truncate text-xs text-[var(--text-muted)]" title={document.hash_sha256}>
        {t("engineHash", { engine: document.modele_embeddings, hash: document.hash_sha256.slice(0, 12) })}
      </p>
    </div>
  );
}
