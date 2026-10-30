/**
 * Dark vector basemap from a Protomaps PMTiles extract for Zagreb, served from this origin
 * (master prompt §4, §7.4). Fonts and sprites are self-hosted under /basemap. When the
 * extract is not installed the map falls back to district outlines on a neutral background.
 */
import { layers, namedFlavor, type Flavor } from "@protomaps/basemaps";
import { addProtocol, type StyleSpecification } from "maplibre-gl";
import { Protocol } from "pmtiles";

export const BASEMAP_PATH = "/tiles/zagreb.pmtiles";

// Protomaps "dark", aligned with the app tokens (§7.2): near-black land, muted streets.
// No POI icons: our own layers show the objects that matter for scoring.
const FLAVOR: Flavor = {
  ...namedFlavor("dark"),
  background: "#0B0D10",
  earth: "#111419",
  water: "#0F1E2B",
  buildings: "#1B2028",
};
delete FLAVOR.pois;

export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0E1115" } }],
};

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

export async function loadBasemapStyle(): Promise<{ style: StyleSpecification; basemap: boolean }> {
  if (!(await basemapAvailable())) return { style: FALLBACK_STYLE, basemap: false };
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
      layers: layers("protomaps", FLAVOR, { lang: "hr" }),
    },
  };
}
