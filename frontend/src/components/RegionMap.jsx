import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import { areaIds } from "../constants/plannerCopy.js";
import places from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";

const regionInfo = {
  east: { place: "haeundae-beach", offset: [26, -45], photo: ["Busan_City_Haeundae_Beach.jpg", "부산광역시", "KOGL 1"] },
  center: { place: "gwangalli-beach", offset: [26, 31], photo: ["Gwangalli_Beach_in_Busan.jpg", "Leeyj0401", "CC BY-SA 4.0"] },
  oldtown: { place: "jagalchi-market", offset: [31, 36], photo: ["Busan_Jagalchi_Market.jpg", "Altostratus", "CC BY-SA 4.0"] },
  downtown: { coordinates: [35.156083, 129.060775], offset: [-15, -39], photo: ["Seomyeon.jpg", "Christophe95", "CC BY-SA 4.0"] },
  songdo: { place: "gamcheon-village", offset: [-22, -16], photo: ["Songdo_Beach_-_panoramio.jpg", "michiel1972", "CC BY-SA 3.0"] },
  estuary: { place: "dadaepo-beach", offset: [0, 0], photo: ["Dadaepo_Beach,_Busan,_Korea.jpg", "Ken Eckert", "CC BY-SA 4.0"] },
  geumjeong: { place: "geumjeong-east-gate", offset: [0, 0], photo: ["Geumjeongsanseong.jpg", "Honza Soukup", "CC BY 2.0"] },
};
const catalog = new Map([...places, ...regionalPlaces].map((place) => [place.place_id, place]));
function regionCoordinates(id) {
  const region = regionInfo[id];
  if (region.coordinates) return region.coordinates;
  const { lat, lng } = catalog.get(region.place);
  return [lat, lng];
}
const regionBounds = L.latLngBounds(areaIds.map(regionCoordinates));

export function RegionChoices({ selected, onChange, copy }) {
  if (!selected.length) return <p className="region-empty-note">{copy.noAreaSelection}</p>;
  return (
    <div className="activity-chips">
      {selected.map((id) => (
        <button key={id} type="button" className="activity-chip region-remove" data-selected="true"
          aria-label={copy.removeArea + " · " + copy.areasList[areaIds.indexOf(id)]}
          onClick={() => onChange(selected.filter((item) => item !== id))}>
          <span>{copy.areasList[areaIds.indexOf(id)]}</span><span className="region-remove-icon" aria-hidden="true">×</span>
        </button>
      ))}
    </div>
  );
}

export default function RegionMap({ mapRef, selected, onChange, copy, onDone, onCancel }) {
  const activeCard = useRef(null);
  const actions = useRef(null);
  const fitMap = useRef(null);
  const labelButtons = useRef({});
  const [layers, setLayers] = useState([]);
  const [preview, setPreview] = useState(null);
  const [missingPhoto, setMissingPhoto] = useState(false);

  function openPreview(id) {
    setMissingPhoto(false);
    setPreview(id);
  }

  useEffect(() => {
    const map = mapRef.current;
    const priorCenter = map.getCenter();
    const priorZoom = map.getZoom();
    const priorZoomSnap = map.options.zoomSnap;
    map.options.zoomSnap = .25;
    const doubleClickZoom = map.doubleClickZoom.enabled();
    map.doubleClickZoom.disable();
    const labels = L.layerGroup().addTo(map);
    function fit() {
      if (!map.getContainer().clientWidth) return;
      map.fitBounds(regionBounds, {
        paddingTopLeft: [53, 115],
        paddingBottomRight: [64, (actions.current?.offsetHeight ?? 80) + 125],
        animate: false,
      });
    }
    fitMap.current = fit;
    setLayers(areaIds.map((id) => {
      const marker = L.marker(regionCoordinates(id), {
        keyboard: false, interactive: false, zIndexOffset: 2000,
        icon: L.divIcon({ className: "region-label-anchor", iconSize: [0, 0] }),
      }).addTo(labels);
      const element = marker.getElement();
      L.DomEvent.disableClickPropagation(element);
      return { id, element };
    }));
    fit();
    map.on("resize", fit);
    return () => {
      fitMap.current = null;
      map.off("resize", fit);
      labels.remove();
      if (doubleClickZoom) map.doubleClickZoom.enable();
      map.options.zoomSnap = priorZoomSnap;
      if (mapRef.current === map) map.setView(priorCenter, priorZoom, { animate: false });
    };
  }, [mapRef]);

  useLayoutEffect(() => {
    const map = mapRef.current;
    if (!map?.getContainer().clientWidth) return;
    fitMap.current?.();
    if (!preview || !activeCard.current) return;
    const cardTop = activeCard.current.getBoundingClientRect().top - map.getContainer().getBoundingClientRect().top;
    const markerBottom = labelButtons.current[preview]?.getBoundingClientRect().bottom;
    const mapTop = map.getContainer().getBoundingClientRect().top;
    const offset = Math.ceil((markerBottom ?? mapTop) - mapTop + 8 - cardTop);
    if (offset > 0) map.panBy([0, offset], { animate: false });
  }, [mapRef, preview, missingPhoto]);

  function closePreview() {
    setPreview(null);
    labelButtons.current[preview]?.focus({ preventScroll: true });
  }

  const index = areaIds.indexOf(preview);
  const photo = regionInfo[preview]?.photo;
  const added = selected.includes(preview);
  return (
    <div className="main-region-picker" aria-label={copy.areas} onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        if (preview) closePreview();
        else onCancel();
      }
    }}>
      {layers.map(({ id, element }, i) => {
        const [x, y] = regionInfo[id].offset;
        const active = selected.includes(id);
        return createPortal(
          <div style={{ "--region-x": `${x}px`, "--region-y": `${y}px` }}>
            {(x || y) !== 0 && <span className="region-marker-tether" aria-hidden="true"
              style={{ width: Math.hypot(x, y), rotate: `${Math.atan2(y, x)}rad` }} />}
            <button type="button" className="region-label" ref={(node) => { labelButtons.current[id] = node; }}
              data-selected={active} aria-expanded={preview === id} aria-controls={preview === id ? "region-preview" : undefined}
              onClick={() => openPreview(id)}>
              <span className="region-illustration">
                <img src={import.meta.env.BASE_URL + "areas/markers/" + id + ".png"} alt="" />
                {active && <span className="region-marker-check" aria-hidden="true">✓</span>}
              </span>
              <span className="region-marker-name">{copy.areasList[i]}</span>
            </button>
          </div>, element, id);
      })}
      <div className="main-region-actions">
        {preview && (
          <section className="region-preview" id="region-preview" ref={activeCard} aria-label={copy.areasList[index]}>
            <button className="region-close" type="button" aria-label={copy.closeArea} onClick={closePreview}>×</button>
            {!missingPhoto && photo && (
              <figure>
                <img key={preview} src={import.meta.env.BASE_URL + "areas/" + preview + ".jpg"} alt="" onError={() => setMissingPhoto(true)} />
                <figcaption><a href={"https://commons.wikimedia.org/wiki/File:" + photo[0]} target="_blank" rel="noreferrer">{photo[1]} · {photo[2]}</a></figcaption>
              </figure>
            )}
            <div className="region-preview-copy">
              <strong>{copy.areasList[index]}</strong>
              <p>{copy.areaDescriptions[index]}</p>
              <button className="region-add" type="button" aria-pressed={added} title={added ? copy.removeArea : undefined} onClick={() => {
                onChange(added ? selected.filter((id) => id !== preview) : [...selected, preview]);
                closePreview();
              }}>
                <span aria-hidden="true">{added ? "✓" : "+"}</span>
                {added ? copy.areaAdded : copy.addArea}
              </button>
            </div>
          </section>
        )}
        <div className="region-session-buttons" ref={actions}>
          <button type="button" onClick={onCancel}>{copy.cancelAreas}</button>
          <button type="button" onClick={onDone}>{copy.doneAreasLabel(selected.length)}</button>
        </div>
      </div>
    </div>
  );
}
