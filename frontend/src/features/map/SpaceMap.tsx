/**
 * MapLibre map of spaces (lazy chunk) on the self-hosted Protomaps basemap, or on D07 district
 * outlines when the extract is not installed (master prompt §7.4); spaces are focusable HTML
 * markers. Reference layers use the same colour as their criterion everywhere in the app.
 */
import "maplibre-gl/dist/maplibre-gl.css";

// The worker is served from this origin as a hashed asset (CSP: script-src 'self').
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

import {
  AttributionControl,
  LngLatBounds,
  Map as MapLibre,
  Marker,
  NavigationControl,
  type GeoJSONSource,
  type StyleSpecification,
  setWorkerUrl,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { CRITERION_COLOR } from "@/lib/labels";
import { useDistrictLayer, usePointLayer } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import type { PointLayerName, Radius } from "@/lib/types";

import { loadBasemapStyle, MAP_COLORS } from "./basemap";

export type MarkerKind = "entrance" | "building" | "district";

export interface MapSpace {
  id: string;
  label: string;
  rank: number | null;
  lon: number;
  lat: number;
  kind: MarkerKind;
}

export interface SpaceMapProps {
  spaces: MapSpace[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  radius: Radius;
  layers: PointLayerName[];
  /** Embedded in a scrolling page: two fingers / Ctrl to move the map. */
  cooperative?: boolean;
  className?: string;
}

setWorkerUrl(workerUrl);

const ZAGREB: [number, number] = [15.98, 45.81];
const LAYER_COLOR: Record<PointLayerName, string> = {
  transit: CRITERION_COLOR.transit,
  parking: CRITERION_COLOR.parking,
  universities: CRITERION_COLOR.universities,
  culture: CRITERION_COLOR.culture,
  schools: CRITERION_COLOR.schools,
};

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Air-distance circle as a 64-gon (metres on a local sphere approximation). */
function circle(lon: number, lat: number, radiusM: number): GeoJSON.Feature<GeoJSON.Polygon> {
  const coords: [number, number][] = [];
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    coords.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [coords] } };
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export default function SpaceMap({
  spaces,
  selectedId,
  onSelect,
  radius,
  layers,
  cooperative = false,
  className = "",
}: SpaceMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibre | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; el: HTMLButtonElement }>());
  const loaded = useRef(false);
  const pending = useRef<((m: MapLibre) => void)[]>([]);
  const fitted = useRef(false);
  // Bumped when the (async) map exists, so the data effects below run again.
  const [ready, setReady] = useState(0);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const theme = useTheme();
  // A theme switch rebuilds the map; keep the visitor's view.
  const view = useRef<{ center: [number, number]; zoom: number } | null>(null);

  const districts = useDistrictLayer();
  const transit = usePointLayer("transit", layers.includes("transit"));
  const parking = usePointLayer("parking", layers.includes("parking"));
  const universities = usePointLayer("universities", layers.includes("universities"));
  const culture = usePointLayer("culture", layers.includes("culture"));
  const schools = usePointLayer("schools", layers.includes("schools"));
  const pointData = { transit, parking, universities, culture, schools };

  // Create the map once, after deciding between the basemap and the fallback style.
  useEffect(() => {
    let cancelled = false;
    let created: MapLibre | null = null;
    const registry = markers.current;
    void loadBasemapStyle(theme).then(({ style, basemap }) => {
      if (cancelled || !container.current) return;
      created = createMap(container.current, style, basemap);
    });
    return () => {
      cancelled = true;
      registry.forEach(({ marker }) => marker.remove());
      registry.clear();
      if (created) {
        const c = created.getCenter();
        view.current = { center: [c.lng, c.lat], zoom: created.getZoom() };
      }
      created?.remove();
      map.current = null;
      loaded.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cooperative, theme]);

  const createMap = (el: HTMLDivElement, style: StyleSpecification, basemap: boolean) => {
    const colors = MAP_COLORS[theme];
    const m = new MapLibre({
      container: el,
      style,
      center: view.current?.center ?? ZAGREB,
      zoom: view.current?.zoom ?? 11,
      minZoom: 9,
      maxZoom: 18,
      maxBounds: [
        [15.6, 45.6],
        [16.4, 46.0],
      ],
      attributionControl: false,
      cooperativeGestures: cooperative,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 0,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.addControl(
      new AttributionControl({
        compact: false,
        customAttribution: "© OpenStreetMap contributors · Grad Zagreb (granice četvrti)",
      }),
      "bottom-right",
    );
    m.on("load", () => {
      m.addSource("districts", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "district-fill",
        type: "fill",
        source: "districts",
        // With streets underneath the districts are outlines only.
        paint: { "fill-color": colors.districtFill, "fill-opacity": basemap ? 0 : 0.9 },
      });
      m.addLayer({
        id: "district-line",
        type: "line",
        source: "districts",
        paint: {
          "line-color": basemap ? colors.outline : colors.districtLine,
          "line-opacity": basemap ? 0.35 : 1,
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1, 14, 2],
        },
      });
      m.addSource("radius", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "radius-fill",
        type: "fill",
        source: "radius",
        paint: { "fill-color": colors.accent, "fill-opacity": 0.08 },
      });
      m.addLayer({
        id: "radius-line",
        type: "line",
        source: "radius",
        paint: { "line-color": colors.accent, "line-width": 1.5, "line-dasharray": [2, 2] },
      });
      for (const name of Object.keys(LAYER_COLOR) as PointLayerName[]) {
        m.addSource(`ref-${name}`, { type: "geojson", data: EMPTY });
        m.addLayer({
          id: `ref-${name}`,
          type: "circle",
          source: `ref-${name}`,
          layout: { visibility: "none" },
          paint: {
            "circle-color": LAYER_COLOR[name],
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 15, 6],
            "circle-opacity": 0.9,
            // Bus stops are hollow so they read differently from tram stops.
            "circle-stroke-color": LAYER_COLOR[name],
            "circle-stroke-width":
              name === "transit" ? ["case", ["==", ["get", "kind"], "bus"], 1, 0] : 0,
          },
        });
        if (name === "transit") {
          m.setPaintProperty("ref-transit", "circle-opacity", [
            "case",
            ["==", ["get", "kind"], "bus"],
            0,
            0.9,
          ]);
        }
      }
      loaded.current = true;
      pending.current.splice(0).forEach((fn) => fn(m));
    });
    const zoomClass = () => container.current?.classList.toggle("map-far", m.getZoom() < 12.5);
    m.on("zoom", zoomClass);
    zoomClass();
    map.current = m;
    setReady((n) => n + 1);
    return m;
  };

  // Run a style update now or once the map has loaded.
  const whenReady = (fn: (m: MapLibre) => void) => {
    const m = map.current;
    if (!m) return;
    if (loaded.current) fn(m);
    else pending.current.push(fn);
  };

  useEffect(() => {
    if (!districts.data) return;
    const data = districts.data as unknown as GeoJSON.FeatureCollection;
    whenReady((m) => (m.getSource("districts") as GeoJSONSource).setData(data));
  }, [districts.data, ready]);

  const layerKey = layers.join(",");
  const dataKey = Object.values(pointData)
    .map((q) => q.dataUpdatedAt)
    .join(",");
  useEffect(() => {
    whenReady((m) => {
      for (const name of Object.keys(LAYER_COLOR) as PointLayerName[]) {
        const on = layers.includes(name);
        m.setLayoutProperty(`ref-${name}`, "visibility", on ? "visible" : "none");
        const data = pointData[name].data;
        if (on && data) (m.getSource(`ref-${name}`) as GeoJSONSource).setData(data);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layerKey, dataKey, ready]);

  // Space markers: rebuilt when the set changes.
  const spacesKey = spaces.map((s) => `${s.id}:${s.rank}:${s.kind}`).join("|");
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const registry = markers.current;
    registry.forEach(({ marker }) => marker.remove());
    registry.clear();
    // Lower ranks on top: add the best last.
    const ordered = [...spaces].sort((a, b) => (b.rank ?? 1e9) - (a.rank ?? 1e9));
    for (const s of ordered) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `map-marker map-marker--${s.kind}`;
      const rank = s.rank !== null ? String(s.rank) : "";
      el.textContent = rank;
      // WCAG 2.5.3: the accessible name starts with the visible rank number.
      const name = rank && !s.label.startsWith(`${rank}.`) ? `${rank}. ${s.label}` : s.label;
      el.setAttribute("aria-label", name);
      el.title = name;
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelectRef.current(s.id);
      });
      const marker = new Marker({ element: el }).setLngLat([s.lon, s.lat]).addTo(m);
      registry.set(s.id, { marker, el });
    }
    if (!fitted.current && spaces.length) {
      fitted.current = true;
      const bounds = new LngLatBounds();
      spaces.forEach((s) => bounds.extend([s.lon, s.lat]));
      m.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spacesKey, ready]);

  // Selection: highlight, radius circle, bring into view.
  useEffect(() => {
    markers.current.forEach(({ el }, id) => {
      const on = id === selectedId;
      el.classList.toggle("is-selected", on);
      el.setAttribute("aria-pressed", String(on));
    });
    const selected = spaces.find((s) => s.id === selectedId);
    whenReady((m) => {
      const source = m.getSource("radius") as GeoJSONSource;
      source.setData(
        selected && selected.kind !== "district"
          ? circle(selected.lon, selected.lat, radius)
          : EMPTY,
      );
      if (selected && !m.getBounds().contains([selected.lon, selected.lat])) {
        m.easeTo({ center: [selected.lon, selected.lat], duration: reducedMotion() ? 0 : 400 });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, radius, spacesKey, ready]);

  return (
    <div
      ref={container}
      className={`space-map relative h-full w-full overflow-hidden ${className}`}
      role="region"
      aria-label="Karta prostora. Isti prostori navedeni su i u popisu."
    />
  );
}
