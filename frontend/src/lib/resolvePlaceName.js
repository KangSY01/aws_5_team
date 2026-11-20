// 장소명 결정 유틸리티: 표시 언어 → en → names 의 첫 유효 값 → place_id 순서

const SUPPORTED = ['ko', 'en', 'ja', 'zh-Hans', 'zh-Hant'];
const DEFAULT_LANGUAGE = 'en';

// 공백만 있는 문자열은 빈 값으로 취급한다
function isUsable(value) {
  return typeof value === 'string' && value.trim() !== '';
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function ownValue(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : undefined;
}

/**
 * places 배열을 Map(place_id → Place) 로 만든다.
 * 앞에서부터 순회하며 place_id 가 아직 없을 때만 set 하므로 중복이면 첫 Place 가 쓰인다.
 * 배열이 아니면 빈 Map 을 반환한다. 입력은 변경하지 않는다.
 */
export function buildPlacesById(places) {
  const map = new Map();
  if (!Array.isArray(places)) return map;
  for (const place of places) {
    if (!isPlainObject(place)) continue;
    if (!map.has(place.place_id)) map.set(place.place_id, place);
  }
  return map;
}

/**
 * @returns {{ name: string, isFallbackToId: boolean }}
 */
export function resolvePlaceName(stop, placesById, language) {
  const placeId = stop?.place_id;
  try {
    const lang = SUPPORTED.includes(language) ? language : DEFAULT_LANGUAGE;
    const place =
      placesById && typeof placesById.get === 'function'
        ? placesById.get(placeId)
        : undefined;
    const names = place?.names;

    if (isPlainObject(names)) {
      const preferred = ownValue(names, lang);
      if (isUsable(preferred)) return { name: preferred, isFallbackToId: false };

      const english = ownValue(names, DEFAULT_LANGUAGE);
      if (isUsable(english)) return { name: english, isFallbackToId: false };

      const first = Object.values(names).find(isUsable);
      if (first !== undefined) return { name: first, isFallbackToId: false };
    }
  } catch {
    // 예외 없이 place_id 대체로 이동
  }
  return { name: placeId, isFallbackToId: true };
}

export default resolvePlaceName;
