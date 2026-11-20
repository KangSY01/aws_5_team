import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";
import RegionMap from "./RegionMap.jsx";

const tileOverride = import.meta.env.VITE_MAP_TILE_URL;
const osmTileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const osmAttribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const tileOverrideAttribution = import.meta.env.VITE_MAP_TILE_ATTRIBUTION;
const pinSize = 44;
const pinAnchor = [22, 42];
const pinGap = pinSize + 4;
const eventIcons = {
  festival: "m12 2 2.3 6.7L21 11l-6.7 2.3L12 20l-2.3-6.7L3 11l6.7-2.3z",
  performance: "M10 17V6l10-2v11M10 17a3 2 0 1 1-6 0 3 2 0 0 1 6 0Zm10-2a3 2 0 1 1-6 0 3 2 0 0 1 6 0Z",
  exhibition: "M4 4h16v16H4zM4 16l5-5 4 4 3-2 4 4M15 8h1",
  market: "M4 10h16l-2-5H6zm2 0v9h12v-9m-7 9v-5h4",
};

export default function BusanMap({ plan, places, events, onEventSelect, language, label, locationCopy, selectedId, nextStopId, onSelect, focusRequest, regionPicker }) {
  const container = useRef(null);
  const mapRef = useRef(null);
  const [locationControl, setLocationControl] = useState(null);
  const [locationStatus, setLocationStatus] = useState("");
  const locationMarker = useRef(null);
  const locationRequest = useRef(false);
  const cancelLocationMove = useRef(null);
  const fittedPlan = useRef(null);
  const markersRef = useRef(new Map());
  const languageRef = useRef(language);
  const updateMapLanguage = useRef(null);
  const updateBridge = useRef(null);
  const selectingRegions = Boolean(regionPicker);
  const selectingRegionsRef = useRef(selectingRegions);

  useEffect(() => {
    selectingRegionsRef.current = selectingRegions;
    updateBridge.current?.();
  }, [selectingRegions]);
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
  const visitSegments = useMemo(() => mappedStops.flatMap(({ coordinates, stop }, index) => {
    const next = mappedStops[index + 1];
    if (!coordinates || !next?.coordinates) return [];
    if (stop.end?.slice(0, 10) !== next.stop.start?.slice(0, 10)) return [];
    return [[coordinates, next.coordinates]];
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
    });
    map.setView([35.135, 129.085], map.getSize().x < 900 ? 11 : 12);
    mapRef.current = map;

    L.control.attribution({ position: "bottomright", prefix: false }).addTo(map);
    const control = L.control({ position: "bottomright" });
    control.onAdd = () => {
      const element = L.DomUtil.create("div", "busan-location-control");
      L.DomEvent.disableClickPropagation(element);
      L.DomEvent.disableScrollPropagation(element);
      return element;
    };
    control.addTo(map);
    setLocationControl(control.getContainer());
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
        const vectorMap = layer.getMaplibreMap();
        const syncBridge = () => {
          if (vectorMap.getLayer("gwangan-bridge")) {
            vectorMap.setLayoutProperty("gwangan-bridge", "visibility", selectingRegionsRef.current ? "none" : "visible");
          }
        };
        updateBridge.current = syncBridge;
        vectorMap.once("style.load", () => {
          updateLanguage();
          syncBridge();
        });
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
      updateBridge.current = null;
      observer?.disconnect();
      cancelLocationMove.current?.();
      cancelLocationMove.current = null;
      locationMarker.current = null;
      locationRequest.current = false;
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
    if (!events?.length) return;
    const map = mapRef.current;
    const layer = L.layerGroup().addTo(map);
    const markers = events.map((event) => {
      const marker = L.marker([event.place.lat, event.place.lng], {
        title: event.names[language],
        zIndexOffset: -10000,
        icon: L.divIcon({
          className: `busan-event-pin busan-event-${event.type}`,
          iconSize: [44, 44],
          iconAnchor: [22, 22],
          html: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${eventIcons[event.type]}"/></svg>`,
        }),
      }).addTo(layer);
      marker.getElement().setAttribute("aria-label", event.names[language]);
      marker.getElement().addEventListener("keydown", (key) => {
        if (key.key === " ") {
          key.preventDefault();
          key.stopPropagation();
          onEventSelect(event);
        }
      });
      marker.on("click", () => onEventSelect(event));
      return marker;
    });
    function updateVisibility() {
      const itinerary = [...markersRef.current.values()].map((marker) => {
        const [x, y] = marker.getElement().style.translate.split(" ").map(parseFloat);
        return map.project(marker.getLatLng()).add([x || 0, (y || 0) - 20]);
      });
      const visible = [];
      const zoom = map.getZoom();
      for (const marker of markers) {
        const point = map.project(marker.getLatLng());
        const overlaps = (points, radius) => points.some((other) => point.distanceTo(other) < radius);
        const show = !overlaps(itinerary, 48) && !overlaps(visible, zoom < 12 ? 85 : 44);
        marker.getElement().hidden = !show;
        if (show) visible.push(point);
      }
    }
    updateVisibility();
    map.on("zoomend", updateVisibility);
    return () => {
      map.off("zoomend", updateVisibility);
      layer.remove();
    };
  }, [events, language, mappedStops, onEventSelect, onSelect]);

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
    const [offsetX, offsetY] = marker.getElement().style.translate.split(" ").map(parseFloat);
    const targetY = Math.max(70, visibleHeight / 2 + 20);
    const center = map.project(marker.getLatLng()).add([offsetX || 0, size.y / 2 - targetY + (offsetY || 0)]);
    map.panTo(map.unproject(center), { animate: !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches });
  }, [focusRequest]);

  function findLocation() {
    const map = mapRef.current;
    if (!map || locationRequest.current) return;
    if (!navigator.geolocation) {
      setLocationStatus("unavailable");
      return;
    }

    locationRequest.current = true;
    setLocationStatus("pending");
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      if (mapRef.current !== map) return;
      locationRequest.current = false;
      setLocationStatus("");
      cancelLocationMove.current?.();
      map.stop();

      const position = L.latLng(coords.latitude, coords.longitude);
      if (!locationMarker.current) {
        locationMarker.current = L.marker(position, {
          interactive: false,
          keyboard: false,
          zIndexOffset: 1200,
          icon: L.divIcon({
            className: "busan-location-pin",
            iconSize: [44, 44],
            iconAnchor: pinAnchor,
            html: `<span class="busan-location-ring"></span><span class="busan-location-ring"></span>
              <svg viewBox="0 0 44 44" aria-hidden="true">
                <path d="M22 42C15 34 7 25 7 18a15 15 0 1 1 30 0c0 7-8 16-15 24Z" />
                <circle cx="22" cy="18" r="4" />
              </svg>`,
          }),
        }).addTo(map);
      } else {
        locationMarker.current.setLatLng(position);
      }

      const pin = locationMarker.current.getElement();
      pin.setAttribute("aria-hidden", "true");
      pin.removeAttribute("data-pulse");
      const size = map.getSize();
      const bounds = container.current.getBoundingClientRect();
      const panel = container.current.closest("main").querySelector(".travel-chat");
      const panelBounds = panel.getBoundingClientRect();
      const covered = !panel.hidden && panelBounds.width > 0 && panelBounds.left < bounds.right;
      const bottomSheet = covered && panelBounds.top > bounds.top;
      const visibleHeight = bottomSheet ? panelBounds.top - bounds.top : size.y;
      const visibleWidth = covered && !bottomSheet ? Math.max(0, panelBounds.left - bounds.left) : size.x;
      const center = map.unproject(map.project(position).add([(size.x - visibleWidth) / 2, (size.y - visibleHeight) / 2]));
      const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      const alreadyCentered = map.project(map.getCenter()).distanceTo(map.project(center)) < 1;

      function pulse() {
        cancelLocationMove.current?.();
        // Flush removal so replay works when the same marker is already centered.
        pin.getBoundingClientRect();
        pin.setAttribute("data-pulse", "");
      }

      if (reducedMotion) {
        map.panTo(center, { animate: false });
      } else if (alreadyCentered) {
        pulse();
      } else {
        cancelLocationMove.current = () => {
          map.off("moveend", pulse);
          cancelLocationMove.current = null;
        };
        map.on("moveend", pulse);
        map.panTo(center, { animate: true, duration: .45 });
      }
    }, (error) => {
      if (mapRef.current !== map) return;
      locationRequest.current = false;
      setLocationStatus(error.code === 1 ? "denied" : "unavailable");
    }, { timeout: 10000, maximumAge: 0 });
  }

  return (
    <>
      <div ref={container} className="busan-map" role="region" aria-label={label} />
      {locationControl && locationCopy && createPortal(
        <>
          <button type="button" aria-label={locationCopy.find} title={locationCopy.find}
            aria-disabled={locationStatus === "pending"} onClick={findLocation}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" />
              <path d="M12 2v3m0 14v3M2 12h3m14 0h3" />
            </svg>
          </button>
          <div className="busan-location-status" role="status">{locationCopy[locationStatus]}</div>
        </>, locationControl
      )}
      {regionPicker && <RegionMap mapRef={mapRef} {...regionPicker} />}
    </>
  );
}
