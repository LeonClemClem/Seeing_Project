import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import { MAP_CENTER, MAP_STYLE_URL } from "../config";
import type { SiteSummary } from "../lib/hooks";
import { seeingBand, seeingColor } from "../lib/seeing";

export default function SiteMap({ summaries }: { summaries: SiteSummary[] }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const fittedFor = useRef(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (!container.current) return;
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({
        container: container.current,
        style: MAP_STYLE_URL,
        center: MAP_CENTER,
        zoom: 4.6,
        attributionControl: { compact: true },
        cooperativeGestures: true,
      });
    } catch (err) {
      // e.g. no WebGL: the site list still works.
      console.warn("Map unavailable", err);
      container.current.textContent = "Map unavailable in this browser.";
      return;
    }
    // The free style references a few sprite icons it does not ship: stub them to keep the console clean.
    instance.on("styleimagemissing", (e) => {
      if (!instance.hasImage(e.id)) instance.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) });
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      fittedFor.current = 0;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = summaries.map(({ site, tonight }) => {
      const value = tonight?.median ?? null;
      const el = document.createElement("button");
      el.className = "map-marker";
      el.style.setProperty("--c", seeingColor(value));
      el.textContent = value != null ? value.toFixed(1) : "–";
      const label = `${site.name}: tonight median ${value != null ? `${value.toFixed(1)}″ (${seeingBand(value)?.label})` : "no data"}`;
      el.title = label;
      el.setAttribute("aria-label", label);
      el.addEventListener("click", () => navigate(`/sites/${site.slug}`));
      return new maplibregl.Marker({ element: el }).setLngLat([site.lon, site.lat]).addTo(m);
    });
    if (summaries.length > 0 && fittedFor.current !== summaries.length) {
      fittedFor.current = summaries.length;
      const bounds = new maplibregl.LngLatBounds();
      summaries.forEach(({ site }) => bounds.extend([site.lon, site.lat]));
      m.fitBounds(bounds, { padding: 40, maxZoom: 7, duration: 0 });
    }
  }, [summaries, navigate]);

  return <div ref={container} className="map" role="region" aria-label="Map of observing sites" />;
}
