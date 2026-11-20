// 데모 스위치 상태 (D). 발표자가 패널에서 고른 기준 시각·날씨를 API 요청의 `demo` 로 넣는다.
// 형식은 docs/api-contract.md 「데모 스위치」: { now: ISO 시각, weather_preset: 이름 }. 생략하거나 null 이면 평소대로.
// `demo` 를 받는 경로는 POST /chat, POST /plan/check, POST /plan/{plan_id}/delay 뿐이다. 다른 경로에는 넣지 않는다.
// React 밖(API 클라이언트)에서도 읽을 수 있게 모듈 상태로 두고, 새로고침해도 남도록 localStorage 에 저장한다.

export const STORAGE_KEY = "busannow.demo";
const KST_OFFSET = "+09:00";

// backend/app/data/weather/ 의 프리셋 파일 이름과 같아야 한다 (없는 이름은 422).
// 날짜 이름 파일(2026-11-28.json 등)은 USE_MOCK=1 의 기본 예보라 여기에 넣지 않는다.
export const WEATHER_PRESETS = [
  { id: null, label: "실제 예보" },
  { id: "rain-afternoon", label: "11/28 13~15시 비" },
];

// 노션 「데모 시나리오 대본」 장면별 기준 시각 (docs/demo-readiness.md 에서 확인한 값).
export const SCENES = [
  { id: "scene1", label: "장면 1·2 일정·혼잡", now: "2026-11-28T09:00:00+09:00", weatherPreset: null },
  { id: "scene5", label: "장면 5 오후 비", now: "2026-11-28T13:00:00+09:00", weatherPreset: "rain-afternoon" },
  { id: "scene6", label: "장면 6 늦었어요", now: "2026-11-28T14:00:00+09:00", weatherPreset: null },
  { id: "scene7", label: "장면 7 귀가", now: "2026-11-28T22:50:00+09:00", weatherPreset: null },
];

const INITIAL = Object.freeze({ enabled: false, now: null, weatherPreset: null });
const PRESET_IDS = new Set(WEATHER_PRESETS.map((p) => p.id));
const ISO_WITH_OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)$/;

let state = load();
const listeners = new Set();

function sanitize(value) {
  const now = typeof value?.now === "string" && ISO_WITH_OFFSET.test(value.now) ? value.now : null;
  const weatherPreset = PRESET_IDS.has(value?.weatherPreset) ? value.weatherPreset : null;
  return Object.freeze({ enabled: value?.enabled === true, now, weatherPreset });
}

function load() {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    return raw ? sanitize(JSON.parse(raw)) : INITIAL;
  } catch {
    return INITIAL; // 저장값이 깨졌으면 꺼진 상태로 시작한다
  }
}

function save() {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 화면 상태만 유지한다
  }
}

function update(next) {
  state = sanitize({ ...state, ...next });
  save();
  listeners.forEach((listener) => listener());
}

export function getDemoState() {
  return state;
}

export function subscribeDemo(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setDemo(next) {
  update(next);
}

export function applyScene(sceneId) {
  const scene = SCENES.find((s) => s.id === sceneId);
  if (scene) update({ enabled: true, now: scene.now, weatherPreset: scene.weatherPreset });
}

export function resetDemo() {
  update(INITIAL);
}

// 테스트용: localStorage 를 다시 읽는다.
export function reloadDemoState() {
  state = load();
  listeners.forEach((listener) => listener());
}

/**
 * API 요청에 넣을 `demo` 값. 스위치가 꺼져 있거나 고른 값이 없으면 null.
 * 예: { now: "2026-11-28T13:00:00+09:00", weather_preset: "rain-afternoon" }
 */
export function getDemoOverride() {
  if (!state.enabled) return null;
  const demo = {};
  if (state.now) demo.now = state.now;
  if (state.weatherPreset) demo.weather_preset = state.weatherPreset;
  return Object.keys(demo).length ? demo : null;
}

/**
 * POST /chat, /plan/check, /plan/{plan_id}/delay 요청 본문에 `demo` 를 붙인다. 꺼져 있으면 본문을 그대로 돌려준다.
 * 사용: body: JSON.stringify(withDemo({ plan_id }))
 */
export function withDemo(body) {
  const demo = getDemoOverride();
  return demo ? { ...body, demo } : body;
}

// <input type="datetime-local"> 값(한국 시각, 초 없음) ↔ ISO 시각(+09:00)
export function toLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000); // KST 벽시계 시각을 UTC 필드로 읽는다
  return kst.toISOString().slice(0, 16);
}

export function fromLocalInput(value) {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value ?? "") ? `${value}:00${KST_OFFSET}` : null;
}
