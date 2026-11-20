import places from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";
import { getActivityCopy } from "../constants/activityCopy.js";
import { activityTextKey, normalizeActivities, placeActivities } from "./activityPreferences.js";

const areas = {
  east: ["haeundae-beach", "haedong-yonggungsa", "shinsegae-centum-city", "coralani"],
  center: ["gwangalli-beach"],
  oldtown: ["gamcheon-village", "jagalchi-market", "busan-tower", "taejongdae", "gukje-market"],
  downtown: ["fm-coffee-house"],
  songdo: ["gamcheon-village", "songdo-beach", "songdo-cable-car"],
  estuary: ["dadaepo-beach", "eulsukdo-eco-park", "busan-moca"],
  geumjeong: ["geumjeong-east-gate", "geumgang-park", "beomeosa-temple"],
};

const catalog = new Map([...places, ...regionalPlaces].filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng))
  .map((place) => [place.place_id, place]));

export function findStopAddition(message, itineraryPlaces) {
  const query = activityTextKey(message);
  const adding = /추가|넣어|\b(?:add|insert|append)\b|追加|加えて|添加|加入|新增|插入/u.test(query);
  if ((!adding && !/가고 싶|추천|알려|\b(?:recommend|visit|where|tell me about)\b|行きたい|おすすめ|想去|推荐|推薦/u.test(query)) ||
      /추가하지|넣지|말고|\b(?:not|without|instead)\b|追加しない|不要添加|不要加入/u.test(query)) return null;
  if (/앞에|이전에|내일|\bbefore\b|\btomorrow\b|の前に|明日|之前|明天/u.test(query)) {
    return adding ? { places: [] } : null;
  }
  const times = [...query.matchAll(
    /(?<!\d)(?:(오전|오후)\s*)?(\d{1,2})\s*시(?:\s*(반|(\d{1,2})\s*분))?|(?<!\d)(\d{1,2}):(\d{2})(?!\d)/gu
  )];
  const suppliedTimes = [...query.matchAll(/\d{1,2}(?::\d{2}|\s*(?:시|時|点|點|am\b|pm\b))/gu)];
  if (times.length > 1 || suppliedTimes.length !== times.length || /\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b/u.test(query)) {
    return adding ? { places: [] } : null;
  }
  let startMinutes;
  if (times.length === 1) {
    const [, period, koreanHour, half, koreanMinute, clockHour, clockMinute] = times[0];
    const hour = Number(koreanHour ?? clockHour);
    const minute = half === "반" ? 30 : Number(koreanMinute ?? clockMinute ?? 0);
    if (hour > 23 || minute > 59 || (period && (hour < 1 || hour > 12))) return { places: [] };
    const baseHour = period ? hour % 12 + (period === "오후" ? 12 : 0) : hour;
    startMinutes = [baseHour * 60 + minute];
    if (!period && koreanHour && hour >= 1 && hour < 12) startMinutes.push((hour + 12) * 60 + minute);
  }
  const compact = query.replace(/\s/g, "");
  const candidates = new Map([...catalog, ...itineraryPlaces.map((place) => [place.place_id, place])]);
  const matches = [...candidates.values()].filter((place) =>
    Object.values(place.names).some((name) => compact.includes(activityTextKey(name).replace(/\s/g, ""))) ||
    (place.place_id === "busan-citizens-park" && compact.includes("시민공원")));
  const category = /카페|\bcaf[eé]s?\b|カフェ|咖啡/u.test(query) ? "cafe"
    : /공원|\bparks?\b|公園|公园/u.test(query) ? "park"
    : /해수욕장|해변|\bbeach(?:es)?\b|ビーチ|海滩|海灘/u.test(query) ? "beach" : null;
  const results = matches.length ? matches : [...candidates.values()].filter((place) => place.category === category);
  return results.length || adding ? { places: results.slice(0, 6), startMinutes, adding, match: matches.length ? "name" : category } : null;
}
const distance = (a, b) => Math.hypot((a.lat - b.lat) * 111, (a.lng - b.lng) * 91);
const demoResponse = () => new Promise((resolve) => setTimeout(resolve, 180));
const aliases = [
  [/골목.*사진|사진.*골목|alley.*photog|photog.*alley|路地.*撮影|巷.*拍照/u, "mural_village"],
  [/사진|photograph|撮影|拍照/u, "photo_spots"],
  [/노을|일몰|sunset|夕日|日落/u, "sunset"],
  [/벽화|mural|壁画|壁畫/u, "mural_village"],
  [/전시|미술관|exhibit|art museum|美術館|美术馆/u, "exhibitions"],
  [/사찰|temple|寺院|寺庙|寺廟/u, "temples"],
];

function activityMatches(text, candidates) {
  const query = activityTextKey(text);
  const named = candidates.filter((place) => Object.values(place.names).some((name) => {
    const key = activityTextKey(name);
    return key.length >= 3 && query.includes(key);
  }));
  if (named.length) return new Set(named.map((place) => place.place_id));
  const tag = aliases.find(([pattern]) => pattern.test(query))?.[1];
  const labels = ["ko", "en", "ja", "zh-Hans", "zh-Hant"].flatMap((language) =>
    Object.entries(getActivityCopy(language).keywords));
  const tags = new Set(tag ? [tag] : labels.filter(([, label]) => query.includes(activityTextKey(label))).map(([id]) => id));
  return new Set(candidates.filter((place) => (placeActivities[place.place_id] ?? []).some((id) => tags.has(id)))
    .map((place) => place.place_id));
}

function kstTime(date, minutes) {
  const localTime = new Date(date.getTime() + minutes * 60000).toISOString().slice(0, 19);
  return localTime + "+09:00";
}

export async function recommendDemo(preferences, language, travelerNotes = "") {
  await demoResponse();
  const areaIds = (preferences.regions.length ? preferences.regions : Object.keys(areas))
    .flatMap((key) => areas[key] ?? []);
  const priorities = new Set(normalizeActivities(preferences.activities));
  const candidates = [...new Set(areaIds)].map((id) => catalog.get(id)).filter(Boolean);
  if (!candidates.length) throw new Error("noPlaces");
  const customMatches = (preferences.customActivities ?? []).map((text) => [text, activityMatches(text, candidates)]);
  const score = (place) => (placeActivities[place.place_id] ?? []).filter((tag) => priorities.has(tag)).length
    + customMatches.filter(([, matches]) => matches.has(place.place_id)).length;
  candidates.sort((a, b) => score(b) - score(a));
  const food = preferences.food ?? "";
  const seafood = /seafood|해산물|海鮮|海鲜/iu;
  const dislikesSeafood = /(?:avoid|no |without|싫|피하|못 먹|빼|제외|避け|不要|不吃).*?(?:seafood|해산물|海鮮|海鲜)|(?:seafood|해산물|海鮮|海鲜).*?(?:allerg|알레르기|빼|제외|못 먹|なし|抜き|过敏|過敏)/iu;
  if (seafood.test(food) && !dislikesSeafood.test(food)) {
    const seafoodMarket = candidates.findIndex((p) => p.place_id === "jagalchi-market");
    if (seafoodMarket !== -1) candidates.unshift(...candidates.splice(seafoodMarket, 1));
  }
  const needsShortWalks = /오래\s*걷기|장거리.*보행|difficulty walking|long distances|長い距離.*歩|长时间步行|長時間步行/iu.test(travelerNotes);
  if (preferences.less_walking || needsShortWalks) {
    const [first, ...others] = candidates;
    others.sort((a, b) => score(b) - score(a) || distance(first, a) - distance(first, b));
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
  const firstHour = priorities.has("night") || priorities.has("sunset") ? (preferences.duration === "half" ? 17 : 13) : 10;
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
    unmatched_activities: customMatches.filter(([, matches]) => !chosen.some((place) => matches.has(place.place_id)))
      .map(([text]) => text),
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
