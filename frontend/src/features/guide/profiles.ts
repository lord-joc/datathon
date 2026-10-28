/**
 * Business profiles shown in step 1. Weights and target areas live in config/profiles.json
 * and will be served by GET /api/v1/profiles (slice 4). This list only drives the UI shell.
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
} from "lucide-react";

export type ProfileCode =
  | "cafe"
  | "office"
  | "retail"
  | "food_takeaway"
  | "personal_care"
  | "education"
  | "workshop";

export interface ProfileOption {
  code: ProfileCode;
  name: string;
  hint: string;
  targetAreaM2: number;
  icon: LucideIcon;
}

export const PROFILES: readonly ProfileOption[] = [
  {
    code: "cafe",
    name: "Kafić / bar",
    hint: "Prijevoz, fakulteti, kultura i okolna ponuda.",
    targetAreaM2: 60,
    icon: Coffee,
  },
  {
    code: "office",
    name: "Ured",
    hint: "Površina, garaža i dostupnost za zaposlenike.",
    targetAreaM2: 80,
    icon: Briefcase,
  },
  {
    code: "retail",
    name: "Trgovina",
    hint: "Ulični položaj i javni prijevoz.",
    targetAreaM2: 50,
    icon: ShoppingBag,
  },
  {
    code: "food_takeaway",
    name: "Pekara / brza hrana",
    hint: "Mali prostor, škole i fakulteti u blizini.",
    targetAreaM2: 35,
    icon: Croissant,
  },
  {
    code: "personal_care",
    name: "Frizerski / kozmetički salon",
    hint: "Lokalna klijentela i manje konkurencije.",
    targetAreaM2: 40,
    icon: Scissors,
  },
  {
    code: "education",
    name: "Edukacija / igraonica",
    hint: "Škole i vrtići u blizini, veća površina.",
    targetAreaM2: 100,
    icon: GraduationCap,
  },
  {
    code: "workshop",
    name: "Radionica / atelier",
    hint: "Površina i garaža važniji od ulice.",
    targetAreaM2: 60,
    icon: Hammer,
  },
];
