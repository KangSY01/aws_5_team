import places from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";

const areas = {
  east: ["haeundae-beach", "haedong-yonggungsa", "shinsegae-centum-city"],
  center: ["gwangalli-beach"],
  oldtown: ["gamcheon-village", "jagalchi-market", "busan-tower", "taejongdae", "gukje-market"],
  downtown: [],
  songdo: ["gamcheon-village", "songdo-beach", "songdo-cable-car"],
  estuary: ["dadaepo-beach", "eulsukdo-eco-park"],
  geumjeong: ["geumjeong-east-gate", "geumgang-park", "beomeosa-temple"],
};

const categories = {
  sea: ["beach", "park"], market: ["market"], cafe: [],
  culture: ["village", "temple", "historic"], active: ["park", "beach", "cable_car"], night: ["observatory", "beach"],
};

const catalog = new Map([...places, ...regionalPlaces].filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng))
  .map((place) => [place.place_id, place]));
const distance = (a, b) => Math.hypot((a.lat - b.lat) * 111, (a.lng - b.lng) * 91);
const demoResponse = () => new Promise((resolve) => setTimeout(resolve, 180));

function kstTime(date, minutes) {
  const localTime = new Date(date.getTime() + minutes * 60000).toISOString().slice(0, 19);
  return localTime + "+09:00";
}

export async function recommendDemo(preferences, language) {
  await demoResponse();
  const areaIds = (preferences.regions.length ? preferences.regions : Object.keys(areas))
    .flatMap((key) => areas[key] ?? []);
  const priorities = preferences.activities.flatMap((key) => categories[key] ?? []);
  const candidates = [...new Set(areaIds)].map((id) => catalog.get(id)).filter(Boolean);
  if (!candidates.length) throw new Error("noPlaces");
  candidates.sort((a, b) => Number(priorities.includes(b.category)) - Number(priorities.includes(a.category)));
  if (/seafood|해산물|海鮮|海鲜/i.test(preferences.food)) {
    const seafoodMarket = candidates.findIndex((p) => p.place_id === "jagalchi-market");
    if (seafoodMarket !== -1) candidates.unshift(...candidates.splice(seafoodMarket, 1));
  }
  if (preferences.less_walking) {
    const [first, ...others] = candidates;
    others.sort((a, b) => distance(first, a) - distance(first, b));
    candidates.splice(1, others.length, ...others);
  }
  const days = { half: 1, day: 1, overnight: 2, long: 3 }[preferences.duration];
  const perDay = Math.max(1, Math.min(preferences.duration === "half" ? 3 : 4, Math.floor(candidates.length / days)));
  const capacity = days * perDay;
  const reserved = new Set();
  for (const region of preferences.regions) {
    if (reserved.size === capacity) break;
    const match = candidates.find((place) => areas[region]?.includes(place.place_id) && !reserved.has(place));
    if (match) reserved.add(match);
  }
  const filled = new Set([...reserved, ...candidates.filter((place) => !reserved.has(place)).slice(0, capacity - reserved.size)]);
  const chosen = candidates.filter((place) => filled.has(place));
  const seoulToday = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
  const start = new Date(seoulToday + "T00:00:00Z");
  const firstHour = preferences.activities.includes("night") ? (preferences.duration === "half" ? 17 : 13) : 10;
  const step = Math.floor((preferences.duration === "half" ? 180 : 420) / perDay);
  const stops = chosen.map((place, index) => {
    const date = new Date(start.getTime() + Math.floor(index / perDay) * 86400000);
    const minutes = firstHour * 60 + (index % perDay) * step;
    return {
      stop_id: "stop-" + (index + 1), place_id: place.place_id, locked: false,
      start: kstTime(date, minutes), end: kstTime(date, minutes + Math.min(60, step - 20)),
    };
  });
  return {
    plan: { plan_id: crypto.randomUUID(), date: seoulToday, profile: { language }, stops },
    places: chosen, demo: true, lodging_unavailable: Boolean(preferences.lodging),
    limited_places: chosen.length < (preferences.duration === "half" ? 3 : 4) * days,
  };
}

export async function suggestDemo({ plan, stop_id, preferences, message }) {
  await demoResponse();
  const index = plan.stops.findIndex((stop) => stop.stop_id === stop_id);
  const target = plan.stops[index];
  if (!target || !catalog.has(target.place_id)) throw new Error("Unknown stop");
  if (target.locked) return { reason_code: "locked", demo: true };
  const used = new Set(plan.stops.map((stop) => stop.place_id));
  const previous = plan.stops[index - 1];
  const next = plan.stops[index + 1];
  const timeLimits = [];
  if (previous && previous.end.slice(0, 10) === target.start.slice(0, 10)) {
    timeLimits.push([catalog.get(previous.place_id), Date.parse(target.start) - Date.parse(previous.end)]);
  }
  if (next && next.start.slice(0, 10) === target.end.slice(0, 10)) {
    timeLimits.push([catalog.get(next.place_id), Date.parse(next.start) - Date.parse(target.end)]);
  }
  if (/vegan|vegetarian|halal|allerg|비건|채식|할랄|알레르기|カフェ|咖啡|cafe|café|카페/i.test(message)) {
    return { reason_code: "catalog_limit", demo: true };
  }
  const askForMarket = /market|lunch|seafood|점심|해산물|시장|市場|午餐|市场/i.test(message);
  const chosenAreas = preferences.regions.flatMap((key) => areas[key] ?? []);
  const fits = [...catalog.values()].filter((place) =>
    !used.has(place.place_id) &&
    (!chosenAreas.length || chosenAreas.includes(place.place_id)) &&
    (!askForMarket || place.category === "market") &&
    timeLimits.every(([other, milliseconds]) => other && distance(place, other) * 1080000 <= milliseconds)
  );
  const original = catalog.get(target.place_id);
  fits.sort((a, b) => distance(a, original) - distance(b, original));
  return fits.length ? { place: fits[0], demo: true } : { reason_code: "no_candidate", demo: true };
}
