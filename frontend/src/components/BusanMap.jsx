import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";

const tileOverride = import.meta.env.VITE_MAP_TILE_URL;
const osmTileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const osmAttribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const tileOverrideAttribution = import.meta.env.VITE_MAP_TILE_ATTRIBUTION;
const pinSize = 44;
const pinAnchor = [22, 42];
const pinGap = pinSize + 4;

export default function BusanMap({ plan, places, language, label, visitOrderLabel, selectedId, nextStopId, onSelect, focusRequest }) {
  const container = useRef(null);
  const mapRef = useRef(null);
  const fittedPlan = useRef(null);
  const markersRef = useRef(new Map());
  const languageRef = useRef(language);
  const updateMapLanguage = useRef(null);
  const mappedStops = useMemo(() => {
    const placesById = buildPlacesById(places);
    return plan.stops.map((stop) => {
      const place = placesById.get(stop.place_id);
      const coordinates = Number.isFinite(place?.lat) && Number.isFinite(place?.lng)
        ? [place.lat, place.lng]
        : null;
      return { stop, coordinates };
    });
  }, [plan, places]);
  const visitSegments = useMemo(() => mappedStops.flatMap(({ coordinates }, index) => {
    const next = mappedStops[index + 1]?.coordinates;
    return coordinates && next ? [[coordinates, next]] : [];
  }), [mappedStops]);

  useEffect(() => {
    languageRef.current = language;
    updateMapLanguage.current?.();
  }, [language]);

  useEffect(() => {
    const map = L.map(container.current, {
      touchZoom: true,
      minZoom: 1,
      maxZoom: 19,
      zoomControl: false,
      attributionControl: false,
    }).setView([35.145, 129.075], 12);
    mapRef.current = map;

    L.control.attribution({ position: "bottomright", prefix: false }).addTo(map);
    const addRaster = () => {
      const url = tileOverride || osmTileUrl;
      const host = new URL(url, window.location.href).hostname;
      const attribution = host === "tile.openstreetmap.org" || host.endsWith(".tile.openstreetmap.org")
        ? osmAttribution
        : tileOverrideAttribution || host;
      L.tileLayer(url, { maxZoom: 19, attribution }).addTo(map);
    };
    let disposed = false;
    const styleRequest = new AbortController();
    if (tileOverride || typeof WebGL2RenderingContext === "undefined") {
      addRaster();
    } else {
      import("./busanBasemap.js").then(async ({ createBusanBasemap, loadBusanStyle }) => {
        if (disposed) return;
        const style = await loadBusanStyle(styleRequest.signal);
        if (disposed) return;
        const { layer, updateLanguage } = createBusanBasemap(style, () => languageRef.current);
        try {
          layer.addTo(map);
        } catch (error) {
          layer.remove();
          throw error;
        }
        updateMapLanguage.current = updateLanguage;
        layer.getMaplibreMap().once("style.load", updateLanguage);
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
      styleRequest.abort();
      updateMapLanguage.current = null;
      observer?.disconnect();
      map.remove();
      mapRef.current = null;
      fittedPlan.current = null;
    };
  }, []);

  useEffect(() => {
    if (!visitSegments.length) return;
    const line = L.polyline(visitSegments, {
      className: "busan-visit-line",
      color: "#387687",
      weight: 2.5,
      opacity: 1,
      dashArray: "2 6",
      lineCap: "round",
      interactive: false,
    }).addTo(mapRef.current);
    return () => line.remove();
  }, [visitSegments]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = L.layerGroup().addTo(map);
    const placesById = buildPlacesById(places);
    const markers = new Map();
    markersRef.current = markers;

    mappedStops.forEach(({ stop, coordinates }, index) => {
      if (!coordinates) return;
      const title = `${index + 1}. ${resolvePlaceName(stop, placesById, language).name}`;
      const marker = L.marker(coordinates, {
        title,
        icon: L.divIcon({
          className: "busan-map-pin",
          iconSize: [pinSize, pinSize],
          iconAnchor: pinAnchor,
          html: `<svg viewBox="0 0 44 44" aria-hidden="true">
            <path d="M22 42C15 34 7 25 7 18a15 15 0 1 1 30 0c0 7-8 16-15 24Z"/>
            <text x="22" y="18" dy=".34em">${index + 1}</text>
          </svg>`,
        }),
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
        const shifts = [[0, 0], [0, -pinGap], [0, pinGap], [-pinGap, 0], [pinGap, 0]];
        for (let step = 2; step <= occupied.length; step += 1) {
          shifts.push([0, -step * pinGap], [0, step * pinGap]);
        }
        const [x, y] = shifts.find(([dx, dy]) =>
          occupied.every((other) =>
            Math.abs(other.x - point.x - dx) >= pinSize || Math.abs(other.y - point.y - dy) >= pinSize
          )
        ) ?? shifts[0];
        occupied.push(point.add([x, y]));
        const element = marker.getElement();
        element.style.translate = `${x}px ${y}px`;
        element.toggleAttribute("data-displaced", Boolean(x || y));
        element.style.setProperty("--pin-tether-length", `${Math.hypot(x, y)}px`);
        element.style.setProperty("--pin-tether-angle", `${Math.atan2(-y, -x)}rad`);
        element.style.setProperty("--pin-origin-x", `${pinAnchor[0] - x}px`);
        element.style.setProperty("--pin-origin-y", `${pinAnchor[1] - y}px`);
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
  }, [plan, places, mappedStops, language, onSelect]);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const active = id === selectedId;
      const element = marker.getElement();
      element?.setAttribute("aria-pressed", String(active));
      element?.toggleAttribute("data-next-stop", id === nextStopId);
      marker.setZIndexOffset(active || id === nextStopId ? 1000 : 0);
    }
  }, [selectedId, nextStopId, plan, places, language, onSelect]);

  useEffect(() => {
    if (!focusRequest) return;
    const map = mapRef.current;
    const marker = markersRef.current.get(focusRequest.id);
    if (!marker) return;

    const size = map.getSize();
    const mapBounds = container.current.getBoundingClientRect();
    const panel = container.current.closest("main").querySelector(".travel-chat");
    const panelBounds = panel.getBoundingClientRect();
    const panelOverlapsMap = !panel.hidden && panelBounds.width > 0 && panelBounds.left < mapBounds.right;
    const visibleHeight = panelOverlapsMap ? panelBounds.top - mapBounds.top : size.y;
    const targetY = Math.max(35, visibleHeight / 2);
    const center = map.project(marker.getLatLng()).add([0, size.y / 2 - targetY]);
    map.panTo(map.unproject(center), { animate: !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches });
  }, [focusRequest]);

  return (
    <div ref={container} className="busan-map" role="region" aria-label={label}>
      {visitSegments.length > 0 && <span className="busan-visit-legend">{visitOrderLabel}</span>}
    </div>
  );
}
