import { useEffect, useMemo, useState } from "react";
import { fetchMapEvents } from "../api/eventsClient.js";
import { buildPlacesById } from "../lib/resolvePlaceName.js";
import places from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";

const catalog = buildPlacesById([...places, ...regionalPlaces]);
const empty = [];
const busanDate = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", dateStyle: "short" });

export function useMapEvents(enabled, demoTime, coursePlaces) {
  const date = busanDate.format(Number.isFinite(demoTime) ? demoTime : Date.now());
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!enabled) return;
    const request = new AbortController();
    fetchMapEvents(date, request.signal).then((events) => {
      if (!request.signal.aborted) setResult({ date, events });
    }).catch(() => {
      if (!request.signal.aborted) setResult({ date, events: empty });
    });
    return () => request.abort();
  }, [date, enabled]);

  return useMemo(() => {
    if (!enabled || result?.date !== date) return empty;
    return result.events.flatMap((event) => {
      if (!event?.contentid || !event.name) return [];
      const place = coursePlaces.get(event.main_place_id) ?? catalog.get(event.main_place_id);
      const coordinates = Number.isFinite(event.lat) && Number.isFinite(event.lng) ? event : place;
      if (!Number.isFinite(coordinates?.lat) || !Number.isFinite(coordinates?.lng)) return [];
      return [{ ...event, lat: coordinates.lat, lng: coordinates.lng, place }];
    });
  }, [coursePlaces, date, enabled, result]);
}
