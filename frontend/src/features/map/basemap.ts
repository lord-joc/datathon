/**
 * Vector basemap from a Protomaps PMTiles extract for Zagreb, served from this origin
 * (master prompt §4, §7.4), in the light or dark flavour of the current theme. Fonts and
 * sprites are self-hosted under /basemap (POI icons are off, so the sprite is never drawn).
 * When the extract is not installed the map falls back to district outlines.
 */
import { layers, namedFlavor, type Flavor } from "@protomaps/basemaps";
import { addProtocol, type StyleSpecification } from "maplibre-gl";
import { Protocol } from "pmtiles";

import type { Theme } from "@/lib/theme";

export const BASEMAP_PATH = "/tiles/zagreb.pmtiles";

// Aligned with the app tokens: quiet land and streets, so the red markers lead.
// No POI icons: our own layers show the objects that matter for scoring.
const FLAVORS: Record<Theme, Flavor> = {
  dark: {
    ...namedFlavor("dark"),
    background: "#0B0D10",
    earth: "#111419",
    water: "#0F1E2B",
    buildings: "#1B2028",
  },
  light: {
    ...namedFlavor("light"),
    background: "#EEF0F3",
    earth: "#F3F4F6",
    water: "#C9DDEB",
    buildings: "#E2E5EA",
  },
};
delete FLAVORS.dark.pois;
delete FLAVORS.light.pois;

/** Colours of our own map layers per theme (districts, radius circle). */
export const MAP_COLORS: Record<
  Theme,
  { districtFill: string; districtLine: string; outline: string; accent: string }
> = {
  dark: { districtFill: "#12151A", districtLine: "#3B4654", outline: "#9AA4B2", accent: "#FF7480" },
  light: {
    districtFill: "#FFFFFF",
    districtLine: "#AFB6C0",
    outline: "#5F6670",
    accent: "#C8102E",
  },
};

export function fallbackStyle(theme: Theme): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": theme === "dark" ? "#0E1115" : "#E6E9ED" },
      },
    ],
  };
}

let registered = false;
let probe: Promise<boolean> | null = null;

/** One small range request decides whether the extract is installed. */
function basemapAvailable(): Promise<boolean> {
  probe ??= fetch(BASEMAP_PATH, { headers: { Range: "bytes=0-6" } })
    .then(
      async (r) => (r.status === 206 || r.status === 200) && (await r.text()).startsWith("PMTiles"),
    )
    .catch(() => false);
  return probe;
}

export async function loadBasemapStyle(
  theme: Theme,
): Promise<{ style: StyleSpecification; basemap: boolean }> {
  if (!(await basemapAvailable())) return { style: fallbackStyle(theme), basemap: false };
  if (!registered) {
    addProtocol("pmtiles", new Protocol().tile);
    registered = true;
  }
  const origin = window.location.origin;
  return {
    basemap: true,
    style: {
      version: 8,
      glyphs: `${origin}/basemap/fonts/{fontstack}/{range}.pbf`,
      sprite: `${origin}/basemap/sprites/dark`,
      sources: {
        protomaps: {
          type: "vector",
          url: `pmtiles://${origin}${BASEMAP_PATH}`,
          attribution:
            '<a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> © <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
        },
      },
      layers: layers("protomaps", FLAVORS[theme], { lang: "hr" }),
    },
  };
}
