export const activityGroups = [
  ["nature", ["beach_walk", "coastal_trail", "wetlands", "light_hike"]],
  ["food", ["market", "street_food", "ocean_cafe", "local_cafe"]],
  ["culture", ["exhibitions", "historic_sites", "temples", "mural_village"]],
  ["experiences", ["water_sports", "cable_car", "workshops", "shopping"]],
  ["evening", ["sunset", "night", "photo_spots", "festivals"]],
];

export const activityIcons = {
  beach_walk: "🏖️", coastal_trail: "🌊", wetlands: "🌿", light_hike: "🥾",
  market: "🛍️", street_food: "🍢", ocean_cafe: "🌅", local_cafe: "☕",
  exhibitions: "🎨", historic_sites: "🏛️", temples: "🛕", mural_village: "🏘️",
  water_sports: "🏄", cable_car: "🚠", workshops: "🧵", shopping: "🛒",
  sunset: "🌇", night: "🌃", photo_spots: "📷", festivals: "🎭",
};

const legacy = {
  sea: ["beach_walk", "coastal_trail", "wetlands"],
  cafe: ["ocean_cafe", "local_cafe"],
  culture: ["historic_sites", "temples", "mural_village"],
  active: ["beach_walk", "wetlands", "light_hike", "cable_car"],
};

export function normalizeActivities(ids = []) {
  return [...new Set(ids.flatMap((id) => Object.hasOwn(legacy, id) ? legacy[id] : [id]))]
    .filter((id) => availableActivities.has(id));
}

export const placeActivities = {
  "haeundae-beach": ["beach_walk", "photo_spots"],
  "gwangalli-beach": ["beach_walk", "night", "photo_spots"],
  "songdo-beach": ["beach_walk"],
  "dadaepo-beach": ["beach_walk", "sunset", "photo_spots"],
  "taejongdae": ["coastal_trail", "photo_spots"],
  "eulsukdo-eco-park": ["wetlands"],
  "geumgang-park": ["light_hike"],
  "jagalchi-market": ["market"],
  "gukje-market": ["market", "street_food"],
  "coralani": ["ocean_cafe"],
  "fm-coffee-house": ["local_cafe"],
  "busan-moca": ["exhibitions"],
  "geumjeong-east-gate": ["historic_sites"],
  "haedong-yonggungsa": ["temples", "photo_spots"],
  "beomeosa-temple": ["temples"],
  "gamcheon-village": ["mural_village", "photo_spots"],
  "songdo-cable-car": ["cable_car"],
  "shinsegae-centum-city": ["shopping"],
  "busan-tower": ["night", "photo_spots"],
};

export const availableActivities = new Set(Object.values(placeActivities).flat());

export function activityTextKey(value) {
  return value.normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();
}
