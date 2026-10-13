import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/ui/StatusBadge";

describe("StatusBadge", () => {
  it("affiche COMPLETE en français", () => {
    render(<StatusBadge status="COMPLETE" />);
    expect(screen.getByText(/Complet/)).toBeInTheDocument();
    expect(screen.getByText(/COMPLETE/)).toBeInTheDocument();
  });

  it("affiche PARTIAL en français", () => {
    render(<StatusBadge status="PARTIAL" />);
    expect(screen.getByText(/Partiel/)).toBeInTheDocument();
  });

  it("affiche NOT_FOUND en français", () => {
    render(<StatusBadge status="NOT_FOUND" />);
    expect(screen.getByText(/Non trouvé/)).toBeInTheDocument();
  });
});
