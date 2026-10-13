import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/actions/locale", () => ({ definirLocale: vi.fn() }));

import { definirLocale } from "@/lib/actions/locale";
import { LocaleSwitcher } from "@/components/layout/LocaleSwitcher";
import { renderAvecIntl } from "./test-utils";

describe("LocaleSwitcher", () => {
  it("propose les 3 langues (fr/en/de) dans leur nom natif", () => {
    renderAvecIntl(<LocaleSwitcher />);
    expect(screen.getByRole("option", { name: "Français" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Deutsch" })).toBeInTheDocument();
  });

  it("affiche la locale courante comme sélectionnée", () => {
    renderAvecIntl(<LocaleSwitcher />, { locale: "de" });
    expect(screen.getByRole("combobox")).toHaveValue("de");
  });

  it("appelle la Server Action definirLocale au changement de langue", () => {
    renderAvecIntl(<LocaleSwitcher />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(definirLocale).toHaveBeenCalledWith("en");
  });

  it("a un libellé accessible (exigence : sélecteur de langue accessible)", () => {
    renderAvecIntl(<LocaleSwitcher />);
    expect(screen.getByRole("combobox", { name: "Langue de l'interface" })).toBeInTheDocument();
  });
});
