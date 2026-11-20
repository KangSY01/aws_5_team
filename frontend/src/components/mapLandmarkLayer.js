import L from "leaflet";
import { mapLandmarks } from "../constants/mapLandmarks.js";

const height = 44;
// 명소 아이콘은 제자리에만 표시 (확대 수준마다 위치가 바뀌지 않도록). 핀·이름표·지명과 겹치면 숨김
const detailOffsets = [[0, 0]];
const labelLayers = ["busan-coastal-districts", "regional-places", "beach-names", "local-places", "stations"];

function overlaps(a, b) {
  return a.left < b.right + 4 && a.right > b.left - 4 &&
    a.top < b.bottom + 4 && a.bottom > b.top - 4;
}

export function addLandmarkLayer(map, language, onSelect) {
  const container = map.getContainer();
  const pane = map.getPane("landmarks") ?? map.createPane("landmarks");
  pane.style.zIndex = "590";
  const layer = L.layerGroup().addTo(map);
  const markers = mapLandmarks.map((landmark) => {
    const marker = L.marker([landmark.lat, landmark.lng], {
      pane: "landmarks",
      bubblingMouseEvents: false,
      icon: L.divIcon({ className: "busan-landmark", iconSize: [landmark.width, height] }),
    }).addTo(layer);
    const element = marker.getElement();
    const image = document.createElement("img");
    image.src = import.meta.env.BASE_URL + "maps/" + landmark.id + ".svg";
    image.alt = "";
    image.draggable = false;
    element.append(image);
    element.hidden = true;
    element.dataset.landmark = landmark.id;
    element.setAttribute("aria-label", landmark.names[language]);
    element.setAttribute("aria-controls", "busan-map-detail");
    marker.on("click", () => onSelect(landmark));
    L.DomEvent.on(element, "keydown", (event) => {
      if (event.key !== " ") return;
      L.DomEvent.stop(event);
      onSelect(landmark);
    });
    return { marker, landmark, element };
  });

  function layout(vectorMap, selectingRegions) {
    const bounds = container.getBoundingClientRect();
    const occupied = [
      ...container.querySelectorAll(".busan-map-pin, .busan-map-pin:not([data-label-hidden]) .busan-map-pin__label, .busan-location-pin, .leaflet-control-zoom"),
      ...container.parentElement.querySelectorAll(".travel-map-tools > button"),
    ]
      .map((element) => element.getBoundingClientRect())
      .filter((rect) => rect.width && rect.height);
    const labels = labelLayers.filter((id) => vectorMap?.getLayer(id));
    const vectorBounds = labels.length && vectorMap.getCanvas().getBoundingClientRect();
    const zoom = map.getZoom();
    const detailZoom = Math.max(10, zoom - (bounds.width >= 900 ? 1 : 0));
    for (const { marker, landmark, element } of markers) {
      const anchor = map.latLngToContainerPoint(marker.getLatLng());
      const halfWidth = landmark.width / 2;
      const centerX = bounds.left + anchor.x;
      const centerY = bounds.top + anchor.y;
      const eligible = !selectingRegions && zoom >= 10 && bounds.width > 0 &&
        detailZoom >= landmark.minZoom &&
        anchor.x >= 0 && anchor.x <= bounds.width && anchor.y >= 0 && anchor.y <= bounds.height;
      let placement;
      if (eligible) {
        const insetX = 0;
        for (const [x, y] of detailOffsets) {
          const dx = insetX + x;
          const rect = { left: centerX + dx - halfWidth, right: centerX + dx + halfWidth,
            top: centerY + y - height / 2, bottom: centerY + y + height / 2 };
          if (rect.left < bounds.left + 4 || rect.right > bounds.right - 4 ||
              rect.top < bounds.top + 60 || rect.bottom > bounds.bottom - 58 ||
              occupied.some((other) => overlaps(rect, other))) continue;
          if (vectorBounds && vectorMap.queryRenderedFeatures([
            [rect.left - vectorBounds.left, rect.top - vectorBounds.top],
            [rect.right - vectorBounds.left, rect.bottom - vectorBounds.top],
          ], { layers: labels }).length) continue;
          placement = { dx, y };
          occupied.push(rect);
          break;
        }
      }
      element.hidden = !placement;
      if (placement) {
        const { dx, y } = placement;
        element.style.translate = `${dx}px ${y}px`;
        element.toggleAttribute("data-offset", Boolean(Math.hypot(dx, y) > 12));
        element.style.setProperty("--landmark-tether", `${Math.hypot(dx, y)}px`);
        element.style.setProperty("--landmark-angle", `${Math.atan2(-y, -dx)}rad`);
      }
    }
  }

  return { layout, remove: () => layer.remove() };
}
