/**
 * Icons for the business profiles. Names, summaries, weights and target areas come from
 * GET /api/v1/profiles (config/profiles.json); only the icon component is resolved here.
 */
import type { LucideIcon } from "lucide-react";
import {
  Briefcase,
  Coffee,
  Croissant,
  GraduationCap,
  Hammer,
  Scissors,
  ShoppingBag,
  Store,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  coffee: Coffee,
  briefcase: Briefcase,
  "shopping-bag": ShoppingBag,
  croissant: Croissant,
  scissors: Scissors,
  "graduation-cap": GraduationCap,
  hammer: Hammer,
};

export function profileIcon(name: string): LucideIcon {
  return ICONS[name] ?? Store;
}
