import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";

const tileOverride = import.meta.env.VITE_MAP_TILE_URL;
const osmAttribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const vectorAttribution = '<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a>';

export default function BusanMap({ plan, places, language, label, selectedId, onSelect, focusRequest }) {
  const container = useRef(null);
  const mapRef = useRef(null);
  const fittedPlan = useRef(null);
  const markersRef = useRef(new Map());

  useEffect(() => {
    const map = L.map(container.current, {
      touchZoom: true,
      minZoom: 1,
      maxZoom: 19,
      zoomControl: false,
      attributionControl: false,
    }).setView([35.145, 129.075], 12);
    mapRef.current = map;

    const attribution = L.control.attribution({ position: "topleft", prefix: false }).addTo(map);
    attribution.addAttribution(osmAttribution);
    const addRaster = () => {
      L.tileLayer(tileOverride || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);
    };
    let disposed = false;
    if (tileOverride || typeof WebGL2RenderingContext === "undefined") {
      addRaster();
    } else {
      import("./busanBasemap.js").then(({ createBusanBasemap }) => {
        if (disposed) return;
        const layer = createBusanBasemap();
        try {
          layer.addTo(map);
        } catch (error) {
          layer.remove();
          throw error;
        }
        attribution.addAttribution(vectorAttribution);
      }).catch(() => {
        if (!disposed) addRaster();
      });
    }
    L.control.zoom({ position: "topright" }).addTo(map);

    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      map.invalidateSize({ pan: false, debounceMoveend: true });
    });
    observer?.observe(container.current);
    return () => {
      disposed = true;
      observer?.disconnect();
      map.remove();
      mapRef.current = null;
      fittedPlan.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = L.layerGroup().addTo(map);
    const placesById = buildPlacesById(places);
    const markers = new Map();
    markersRef.current = markers;

    plan.stops.forEach((stop, index) => {
      const place = placesById.get(stop.place_id);
      if (!Number.isFinite(place?.lat) || !Number.isFinite(place?.lng)) return;
      const title = `${index + 1}. ${resolvePlaceName(stop, placesById, language).name}`;
      const number = document.createElement("span");
      number.textContent = String(index + 1);
      const marker = L.marker([place.lat, place.lng], {
        title,
        icon: L.divIcon({ className: "busan-map-pin", html: number, iconSize: [44, 44], iconAnchor: [22, 22] }),
      }).addTo(layer);
      const element = marker.getElement();
      element.setAttribute("aria-label", title);
      marker.on("click", () => onSelect(stop.stop_id));
      // Leaflet already handles Enter for keyboard-enabled markers.
      element.addEventListener("keydown", (event) => {
        if (event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          onSelect(stop.stop_id);
        }
      });
      markers.set(stop.stop_id, marker);
    });

    function separatePins() {
      const occupied = [];
      for (const marker of markers.values()) {
        const point = map.project(marker.getLatLng());
        const shifts = [[0, 0], [0, -48], [0, 48], [-48, 0], [48, 0], [0, -96], [0, 96]];
        const [x, y] = shifts.find(([dx, dy]) =>
          occupied.every((other) =>
            Math.abs(other.x - point.x - dx) >= 44 || Math.abs(other.y - point.y - dy) >= 44
          )
        ) ?? shifts[0];
        occupied.push(point.add([x, y]));
        marker.getElement().style.translate = `${x}px ${y}px`;
      }
    }

    if (fittedPlan.current !== plan && map.getSize().x > 0 && markers.size) {
      map.fitBounds([...markers.values()].map((marker) => marker.getLatLng()), {
        padding: [42, 80], maxZoom: 12, animate: false,
      });
      fittedPlan.current = plan;
    }
    separatePins();
    map.on("zoomend", separatePins);
    return () => {
      map.off("zoomend", separatePins);
      layer.remove();
    };
  }, [plan, places, language, onSelect]);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const active = id === selectedId;
      marker.getElement()?.setAttribute("aria-pressed", String(active));
      marker.setZIndexOffset(active ? 1000 : 0);
    }
  }, [selectedId, plan, places, language, onSelect]);

  useEffect(() => {
    if (!focusRequest) return;
    const map = mapRef.current;
    const marker = markersRef.current.get(focusRequest.id);
    if (!marker) return;

    const size = map.getSize();
    const mapBounds = container.current.getBoundingClientRect();
    const panelBounds = container.current.closest("main").querySelector(".travel-chat").getBoundingClientRect();
    const panelOverlapsMap = panelBounds.width > 0 && panelBounds.left < mapBounds.right;
    const visibleHeight = panelOverlapsMap ? panelBounds.top - mapBounds.top : size.y;
    const targetY = Math.max(35, visibleHeight / 2);
    const center = map.project(marker.getLatLng()).add([0, size.y / 2 - targetY]);
    map.panTo(map.unproject(center), { animate: !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches });
  }, [focusRequest]);

  return <div ref={container} className="busan-map" role="region" aria-label={label} />;
}
