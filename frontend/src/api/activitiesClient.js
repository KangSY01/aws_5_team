import { requestJson } from "./planClient.js";

const types = [
  ["board_game", /보드\s*게임|board\s*games?|ボードゲーム|桌游|桌遊/iu],
  ["escape_room", /방\s*탈출|escape\s*rooms?|脱出ゲーム|密室逃脫|密室逃脱/iu],
  ["animal_cafe", /동물.{0,5}카페|고양이.{0,5}카페|animal\s*caf[eé]|cat\s*caf[eé]|猫カフェ|貓咖|猫咖/iu],
  ["scenic_cafe", /분위기.{0,8}카페|뷰.{0,5}카페|scenic\s*caf[eé]|おしゃれ.{0,4}カフェ|氛围咖啡|氛圍咖啡/iu],
];

const areas = [
  ["해운대", /해운대|haeundae|海雲台|海云台/iu], ["광안리", /광안리|gwangalli|広安里|廣安里|广安里/iu],
  ["서면", /서면|seomyeon|西面/iu], ["전포", /전포|jeonpo|田浦/iu], ["남포", /남포|nampo|南浦/iu],
  ["영도", /영도|yeongdo|影島|影岛/iu], ["기장", /기장|gijang|機張|机张/iu], ["송정", /송정|songjeong|松亭/iu],
  ["센텀", /센텀|centum/iu], ["부산역", /부산역|busan station|釜山駅|釜山站/iu],
];

export function activitySearch(message) {
  if (/추가|넣어|追加|添加|加入|新增|\b(?:add|insert|append)\b/iu.test(message)) return null;
  const selected = types.filter(([, pattern]) => pattern.test(message));
  const kinds = selected.length ? selected : /놀\s*거리|things to do|fun activities|遊び場|好玩的/iu.test(message) ? types : [];
  if (!kinds.length) return null;
  return { area: areas.find(([, pattern]) => pattern.test(message))?.[0] ?? "부산", kinds: kinds.map(([kind]) => kind) };
}

export async function fetchActivities({ area, kinds }) {
  const responses = await Promise.allSettled(kinds.map((kind) =>
    requestJson("/activities?" + new URLSearchParams({ area, kind }))));
  const places = new Map();
  for (const response of responses) {
    if (response.status !== "fulfilled" || !Array.isArray(response.value?.places)) continue;
    for (const place of response.value.places.slice(0, kinds.length > 1 ? 2 : 5)) {
      if (!place?.name || !/^https:\/\/place\.map\.kakao\.com\/\d+$/.test(place.url)) continue;
      places.set(place.id, { place: {
        place_id: "kakao-" + place.id, names: { ko: place.name }, categoryLabel: place.category?.split(">").at(-1).trim(),
        address: place.address, phone: place.phone, url: place.url,
      } });
    }
  }
  return { options: [...places.values()], unavailable: responses.some(({ status }) => status === "rejected") };
}
