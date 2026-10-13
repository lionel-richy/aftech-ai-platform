import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { renderAvecIntl } from "./test-utils";

describe("StatusBadge", () => {
  it("affiche COMPLETE en français", () => {
    renderAvecIntl(<StatusBadge status="COMPLETE" />);
    expect(screen.getByText(/Complet/)).toBeInTheDocument();
    expect(screen.getByText(/COMPLETE/)).toBeInTheDocument();
  });

  it("affiche PARTIAL en français", () => {
    renderAvecIntl(<StatusBadge status="PARTIAL" />);
    expect(screen.getByText(/Partiel/)).toBeInTheDocument();
  });

  it("affiche NOT_FOUND en français", () => {
    renderAvecIntl(<StatusBadge status="NOT_FOUND" />);
    expect(screen.getByText(/Non trouvé/)).toBeInTheDocument();
  });

  it("affiche COMPLETE en anglais quand la locale est 'en'", () => {
    renderAvecIntl(<StatusBadge status="COMPLETE" />, { locale: "en" });
    expect(screen.getByText(/Complete/)).toBeInTheDocument();
  });

  it("affiche NOT_FOUND en allemand quand la locale est 'de'", () => {
    renderAvecIntl(<StatusBadge status="NOT_FOUND" />, { locale: "de" });
    expect(screen.getByText(/Nicht gefunden/)).toBeInTheDocument();
  });
});
