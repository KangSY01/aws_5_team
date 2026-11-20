import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

const localeFields = {
  ko: ["name:ko", "name_ko"],
  en: ["name:en", "name_en", "name:latin"],
  ja: ["name:ja", "name_ja"],
  "zh-Hans": ["name:zh-Hans", "name_zh-Hans", "name:zh", "name_zh"],
  "zh-Hant": ["name:zh-Hant", "name_zh-Hant"],
};

export async function loadBusanStyle(signal) {
  const url = new URL(import.meta.env.BASE_URL + "maps/busan-poster.json", window.location.href);
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error("Unable to load the Busan map style");
  return response.json();
}

export function createBusanBasemap(style, getLanguage) {
  setWorkerUrl(workerUrl);
  const labelLayers = style.layers.filter((layer) => layer.layout?.["text-field"]);
  const layer = maplibreGL({ style, interactive: false });

  function updateLanguage() {
    const map = layer.getMaplibreMap();
    if (!map?.getStyle()) return;
    const fields = [...(localeFields[getLanguage()] ?? []), "name", "name:latin"];
    const text = ["coalesce", ...fields.map((name) => ["get", name])];
    for (const label of labelLayers) {
      if (map.getLayer(label.id)) map.setLayoutProperty(label.id, "text-field", text);
    }
  }

  return { layer, updateLanguage };
}
