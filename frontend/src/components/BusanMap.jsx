import { fetchRoute } from "../api/routeClient.js";
import { hasConfiguredPlanApi } from "../api/planClient.js";
import { eventName, findStopEvent } from "../lib/stopEvent.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";
import { stopDate } from "../lib/itineraryTiming.js";
import RegionMap from "./RegionMap.jsx";
import { addLandmarkLayer } from "./mapLandmarkLayer.js";

const tileOverride = import.meta.env.VITE_MAP_TILE_URL;
const osmTileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const osmAttribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const tileOverrideAttribution = import.meta.env.VITE_MAP_TILE_ATTRIBUTION;
const pinSize = 44;
const pinAnchor = [22, 42];
// 일정 마커는 둥근 사각 타일이라 가운데가 장소 위치다 (디자인 실험)
const stopPinAnchor = [22, 22];
const pinGap = pinSize + 4;

// 마커 이름표에 넣는 장소 이름을 HTML 로 안전하게 만든다 (디자인 실험)
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export default function BusanMap({ plan, places, events, onLandmarkSelect, language, label, locationCopy, selectedId, nextStopId, onSelect, onRoutes, focusRequest, regionPicker, crowdLevels = null, returnPaths }) {
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
  const updateLandmarks = useRef(null);
  const vectorMapRef = useRef(null);
  const selectingRegions = Boolean(regionPicker);
  const selectingRegionsRef = useRef(selectingRegions);

  useEffect(() => {
    selectingRegionsRef.current = selectingRegions;
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
    if (stopDate(stop.start) !== stopDate(next.stop.start)) return [];
    return [[coordinates, next.coordinates]];
  }), [mappedStops]);
  // visitSegments 와 같은 순서의 출발 일정 stop_id (일정 목록의 구간 안내용)
  const visitStopIds = useMemo(() => mappedStops.flatMap(({ coordinates, stop }, index) => {
    const next = mappedStops[index + 1];
    if (!coordinates || !next?.coordinates) return [];
    if (stopDate(stop.start) !== stopDate(next.stop.start)) return [];
    return [stop.stop_id];
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
        vectorMapRef.current = vectorMap;
        vectorMap.on("idle", () => updateLandmarks.current?.());
        vectorMap.once("style.load", () => {
          updateLanguage();
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
      vectorMapRef.current = null;
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

  // 실제 이동 경로 (GET /route): 도보는 OSM 길, 대중교통은 카카오 노선. 받기 전·실패한 구간은 직선 점선
  const [routes, setRoutes] = useState([]);
  useEffect(() => {
    setRoutes([]);
    if (!visitSegments.length || !hasConfiguredPlanApi()) return;
    const request = new AbortController();
    Promise.all(visitSegments.map(([from, to]) => fetchRoute(from, to, request.signal).catch(() => null)))
      .then((result) => { if (!request.signal.aborted) setRoutes(result); });
    return () => request.abort();
  }, [visitSegments]);

  const onRoutesRef = useRef(onRoutes);
  onRoutesRef.current = onRoutes;
  useEffect(() => {
    onRoutesRef.current?.(Object.fromEntries(visitStopIds.flatMap((id, index) => routes[index] ? [[id, routes[index]]] : [])));
  }, [routes, visitStopIds]);

  useEffect(() => {
    if (!visitSegments.length) return;
    const layer = L.layerGroup().addTo(mapRef.current);
    visitSegments.forEach((segment, index) => {
      const route = routes[index];
      const parts = route?.source !== "straight" && route?.segments?.length
        ? route.segments.map((part) => ({ path: part.path, walking: part.mode === "WALKING" }))
        : [{ path: segment, walking: true, straight: true }];
      for (const part of parts) {
        L.polyline(part.path, {
          className: part.walking ? (part.straight ? "busan-visit-line" : "busan-walk-line") : "busan-transit-line",
          color: part.walking ? "#387687" : "#1c2433",
          weight: part.walking ? 3 : 5,
          opacity: 1,
          dashArray: part.walking ? "2 6" : undefined,
          lineCap: "round",
          lineJoin: "round",
          interactive: false,
        }).addTo(layer);
      }
    });
    return () => layer.remove();
  }, [visitSegments, routes]);

  useEffect(() => {
    if (!returnPaths?.length) return;
    const map = mapRef.current;
    const line = L.polyline(returnPaths, {
      color: "#145440", weight: 4, dashArray: "6 5", interactive: false, attribution: "© TMAP",
    }).addTo(map);
    map.fitBounds(line.getBounds(), { padding: [42, 82], maxZoom: 16, animate: false });
    return () => line.remove();
  }, [returnPaths]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = L.layerGroup().addTo(map);
    const placesById = buildPlacesById(places);
    const markers = new Map();
    markersRef.current = markers;

    mappedStops.forEach(({ stop, coordinates }, index) => {
      if (!coordinates) return;
      const stopEvent = findStopEvent(stop, events);
      const placeName = stopEvent ? eventName(stopEvent, language) : resolvePlaceName(stop, placesById, language).name;
      const title = `${index + 1}. ${placeName}`;
      const marker = L.marker(coordinates, {
        title,
        icon: L.divIcon({
          className: "busan-map-pin",
          iconSize: [pinSize, pinSize],
          iconAnchor: stopPinAnchor,
          html: `<svg viewBox="0 0 44 44" aria-hidden="true">
            <rect x="8" y="8" width="28" height="28" rx="7"/>
            <text x="22" y="22" dy=".34em">${index + 1}</text>
          </svg><span class="busan-map-pin__label" aria-hidden="true">${escapeHtml(placeName)}</span>`,
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
        element.style.setProperty("--pin-origin-x", `${stopPinAnchor[0] - x}px`);
        element.style.setProperty("--pin-origin-y", `${stopPinAnchor[1] - y}px`);
      }
    }

    if (fittedPlan.current !== plan && map.getSize().x > 0 && markers.size) {
      map.fitBounds([...markers.values()].map((marker) => marker.getLatLng()), {
        padding: [42, 80], maxZoom: 12, animate: false,
      });
      fittedPlan.current = plan;
    }
    // 이름표가 지도 오른쪽 끝을 넘으면 핀 왼쪽에 붙인다 (디자인 실험, 모바일에서 잘리지 않게)
    function placeLabels() {
      const width = map.getSize().x;
      for (const marker of markers.values()) {
        const element = marker.getElement();
        const label = element?.querySelector(".busan-map-pin__label");
        if (!label) continue;
        const [x] = (element.style.translate || "0px").split(" ").map(parseFloat);
        const right = map.latLngToContainerPoint(marker.getLatLng()).x + (x || 0) + pinSize / 2 + label.offsetWidth;
        element.toggleAttribute("data-label-left", right > width - 8);
      }
    }

    separatePins();
    placeLabels();
    map.on("zoomend", separatePins);
    map.on("moveend zoomend resize", placeLabels);
    return () => {
      map.off("zoomend", separatePins);
      map.off("moveend zoomend resize", placeLabels);
      layer.remove();
    };
  }, [plan, places, mappedStops, language, onSelect, events]);

  useEffect(() => {
    if (!onLandmarkSelect) return;
    const map = mapRef.current;
    const landmarks = addLandmarkLayer(map, language, onLandmarkSelect);
    const layout = () => landmarks.layout(vectorMapRef.current, selectingRegionsRef.current);
    updateLandmarks.current = layout;
    map.on("moveend resize", layout);
    return () => {
      map.off("moveend resize", layout);
      updateLandmarks.current = null;
      landmarks.remove();
    };
  }, [language, onLandmarkSelect]);

  useEffect(() => {
    updateLandmarks.current?.();
  }, [language, onLandmarkSelect, selectingRegions, mappedStops, onSelect]);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const active = id === selectedId;
      const element = marker.getElement();
      element?.setAttribute("aria-pressed", String(active));
      element?.toggleAttribute("data-next-stop", id === nextStopId);
      if (id === nextStopId) element?.setAttribute("aria-current", "true");
      else element?.removeAttribute("aria-current");
      marker.setZIndexOffset(id === nextStopId ? 2000 : active ? 1000 : 0);
      if (element && crowdLevels?.[id]) element.dataset.crowd = crowdLevels[id];
      else element?.removeAttribute("data-crowd");
    }
  }, [selectedId, nextStopId, plan, places, language, onSelect, crowdLevels]);

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
      updateLandmarks.current?.();

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
