// 출처 표시와 비 예보 배너 문구 (D). 언어 키는 constants/travelCopy.js 의 languages 와 같다.

// 채팅 응답 sources[].tool → 데이터 제공 기관. docs/data-sources.md 「출처별 사용처」 기준.
// 코드가 계산한 값만 쓰는 도구(get_travel_time)와 일정 도구(create_plan 등)는 출처로 보여 주지 않는다.
export const TOOL_PROVIDERS = {
  search_places: ["kto"],
  get_place_info: ["kto"],
  get_hours: ["kto"],
  get_restaurants: ["kto"],
  get_events: ["kto"],
  get_crowd: ["kto"],
  get_weather: ["kma"],
  get_transit_info: ["btc"],
  get_return_options: ["kakao", "btc"],
};

export const PROVIDERS = {
  kto: {
    ko: "한국관광공사",
    en: "Korea Tourism Organization",
    ja: "韓国観光公社",
    "zh-Hans": "韩国观光公社",
    "zh-Hant": "韓國觀光公社",
  },
  kma: {
    ko: "기상청",
    en: "Korea Meteorological Administration",
    ja: "韓国気象庁",
    "zh-Hans": "韩国气象厅",
    "zh-Hant": "韓國氣象廳",
  },
  btc: {
    ko: "부산교통공사",
    en: "Busan Transportation Corporation",
    ja: "釜山交通公社",
    "zh-Hans": "釜山交通公社",
    "zh-Hant": "釜山交通公社",
  },
  kakao: {
    ko: "카카오맵",
    en: "Kakao Map",
    ja: "カカオマップ",
    "zh-Hans": "Kakao 地图",
    "zh-Hant": "Kakao 地圖",
  },
};

export const SOURCES_LABEL = { ko: "출처", en: "Sources", ja: "出典", "zh-Hans": "来源", "zh-Hant": "來源" };

// 배너를 띄우는 데모 날씨 프리셋과 비 시간대. backend/app/data/weather/rain-afternoon.json 의 강수 시각(13·14시) 기준.
export const RAIN_PRESETS = {
  "rain-afternoon": { start: "13:00", end: "15:00" },
};

// 비 예보 배너. 예보가 "바뀌었다"는 것은 알 수 없으므로 "예보가 있다"고만 말한다.
// detail(time, place): place 가 없으면 시간대만 말한다.
export const RAIN_COPY = {
  ko: {
    title: "비 예보가 있어요",
    detail: (time, place) => (place ? `${place} 방문 시간(${time})에 비가 올 수 있어요.` : `오후 ${time}에 비가 올 수 있어요.`),
    open: "대안 보기", close: "닫기",
  },
  en: {
    title: "Rain in the forecast",
    detail: (time, place) => (place ? `Rain may fall during your visit to ${place} (${time}).` : `Rain may fall this afternoon (${time}).`),
    open: "See options", close: "Close",
  },
  ja: {
    title: "雨の予報があります",
    detail: (time, place) => (place ? `${place}の訪問時間（${time}）に雨が降るかもしれません。` : `午後（${time}）に雨が降るかもしれません。`),
    open: "代わりの案を見る", close: "閉じる",
  },
  "zh-Hans": {
    title: "有降雨预报",
    detail: (time, place) => (place ? `游览${place}期间（${time}）可能下雨。` : `下午（${time}）可能下雨。`),
    open: "查看替代方案", close: "关闭",
  },
  "zh-Hant": {
    title: "有降雨預報",
    detail: (time, place) => (place ? `遊覽${place}期間（${time}）可能下雨。` : `下午（${time}）可能下雨。`),
    open: "查看替代方案", close: "關閉",
  },
};

export function pick(table, language) {
  return table[language] ?? table.en;
}

/** sources 를 제공 기관 이름 목록으로 바꾼다. 처음 나온 순서를 지키고 중복은 뺀다. */
export function providerNames(sources, language) {
  const keys = [];
  for (const source of Array.isArray(sources) ? sources : []) {
    for (const key of TOOL_PROVIDERS[source?.tool] ?? []) {
      if (!keys.includes(key)) keys.push(key);
    }
  }
  return keys.map((key) => pick(PROVIDERS[key], language));
}
