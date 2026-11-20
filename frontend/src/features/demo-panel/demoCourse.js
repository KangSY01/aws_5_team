import places from "../../mocks/places.json";

export const demoItineraryPrompt = "11月28日(土)に釜山で一日過ごしたいです。海が見える所と、夜は光の祭りに行きたいです。辛いものは苦手です。";

// Mirrors the backend's scripted itinerary in app/chat/demo_cache.py.
export function makeLocalDemoCourse() {
  const date = "2026-11-28";
  const stops = [
    ["dongbaekseom", "10:00", "11:30"],
    ["haeundae-rodeo-street", "12:00", "13:00"],
    ["haeundae-beach", "14:30", "16:00"],
    ["haeundae-beach", "17:30", "19:30"],
  ].map(([place_id, start, end], index) => ({
    stop_id: "s" + (index + 1), place_id, start: date + "T" + start + ":00+09:00",
    end: date + "T" + end + ":00+09:00", locked: false,
  }));
  return {
    demo: true,
    plan: { plan_id: crypto.randomUUID(), date, profile: { language: "ja" }, stops },
    places: places.filter((place) => stops.some((stop) => stop.place_id === place.place_id)),
  };
}
