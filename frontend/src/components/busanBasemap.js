import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

const style = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    openmaptiles: { type: "vector", url: "https://tiles.openfreemap.org/planet" },
  },
  layers: [
    { id: "land", type: "background", paint: { "background-color": "#F5F5F1" } },
    {
      id: "green-space", type: "fill", source: "openmaptiles", "source-layer": "landcover",
      minzoom: 10, paint: { "fill-color": "#DFE8DA" },
    },
    {
      id: "water", type: "fill", source: "openmaptiles", "source-layer": "water",
      paint: { "fill-color": "#C6E0EB" },
    },
    {
      id: "waterways", type: "line", source: "openmaptiles", "source-layer": "waterway",
      minzoom: 11, paint: { "line-color": "#C6E0EB", "line-width": 1 },
    },
    {
      id: "minor-roads", type: "line", source: "openmaptiles", "source-layer": "transportation",
      minzoom: 14,
      filter: ["==", ["get", "class"], "minor"],
      paint: { "line-color": "#E7E8E5", "line-width": 1 },
    },
    {
      id: "main-roads", type: "line", source: "openmaptiles", "source-layer": "transportation",
      minzoom: 7,
      filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary", "tertiary"]]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#C9D0D2",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 13, 1.2, 17, 2.6],
      },
    },
    {
      id: "major-places", type: "symbol", source: "openmaptiles", "source-layer": "place",
      minzoom: 7,
      filter: ["in", ["get", "class"], ["literal", ["city", "town", "suburb"]]],
      layout: {
        "text-field": ["coalesce", ["get", "name"], ["get", "name:latin"]],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["match", ["get", "class"], "city", 14, 11],
        "text-padding": 14,
      },
      paint: { "text-color": "#4F5B60", "text-halo-color": "#F5F5F1", "text-halo-width": 1.25 },
    },
  ],
};

export function createBusanBasemap() {
  setWorkerUrl(workerUrl);
  return maplibreGL({ style, interactive: false, attributionControl: false });
}
