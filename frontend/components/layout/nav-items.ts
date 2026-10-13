import type { LucideIcon } from "lucide-react";
import { Blocks, LayoutDashboard, Library, MessageSquare, ShieldCheck } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/assistant", label: "Assistant IA", icon: MessageSquare },
  { href: "/bibliotheque", label: "Bibliothèque", icon: Library },
  { href: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { href: "/administration", label: "Administration", icon: ShieldCheck },
  { href: "/integrations", label: "Intégrations", icon: Blocks },
];
