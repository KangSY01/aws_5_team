import places from "./places.json";

const events = [
  ["festival", "haeundae-beach", "2026-11-21", "2026-11-22", ["해운대 바다 축제","Haeundae Seaside Festival","海雲台シーサイド祭り","海云台海滨节","海雲臺海濱節"]],
  ["performance", "gwangalli-beach", "2026-11-21", "2026-11-21", ["광안리 해변 공연","Gwangalli Beach Performance","広安里ビーチ公演","广安里海滩演出","廣安里海灘演出"]],
  ["exhibition", "gamcheon-village", "2026-11-21", "2026-11-29", ["감천 골목 전시","Gamcheon Alley Exhibition","甘川路地の展覧会","甘川小巷展览","甘川巷弄展覽"]],
  ["market", "gukje-market", "2026-11-22", "2026-11-22", ["국제시장 주말 마켓","Gukje Weekend Market","国際市場ウィークエンドマーケット","国际市场周末集市","國際市場週末市集"]],
];

export default events.map(([type, placeId, from, to, names]) => {
  const place = places.find(({ place_id }) => place_id === placeId);
  const locales = ["ko", "en", "ja", "zh-Hans", "zh-Hant"];
  return { type, id: placeId, from, to, place, names: Object.fromEntries(locales.map((code, i) => [code, names[i]])) };
});
