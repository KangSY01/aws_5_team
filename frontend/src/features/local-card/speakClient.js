// POST /speak 호출 (D). 형식은 docs/api-contract.md 「POST /speak」: { text, language } → { content_type, audio_base64 }.
// 현지인 카드는 language "ko" 로 한국어 음성을 받는다. 같은 문장은 한 번만 받아 재사용한다.
import { getBaseUrl } from "../../api/planClient.js";

const TIMEOUT_MS = 10000;
const MAX_TEXT = 500; // 계약: text 1~500자
const cache = new Map(); // `${language}:${text}` → data URL

export class SpeakError extends Error {
  constructor(kind, message) {
    super(message ?? `음성 요청 실패: ${kind}`);
    this.name = "SpeakError";
    this.kind = kind; // "invalid_text" | "network" | "timeout" | "http" | "invalid_response"
  }
}

/**
 * 문장을 음성 data URL(`data:audio/mpeg;base64,...`)로 받는다. 실패하면 SpeakError.
 * options.baseUrl 로 주소를 바꿀 수 있다 (기본: VITE_API_BASE_URL 또는 로컬 백엔드).
 */
export async function fetchSpeech(text, language = "ko", { baseUrl, fetchImpl = globalThis.fetch } = {}) {
  const trimmed = typeof text === "string" ? text.trim() : "";
  if (!trimmed || trimmed.length > MAX_TEXT) throw new SpeakError("invalid_text", "문장은 1~500자여야 합니다.");
  const key = `${language}:${trimmed}`;
  if (cache.has(key)) return cache.get(key);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetchImpl(`${(baseUrl ?? getBaseUrl()).replace(/\/+$/, "")}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: trimmed, language }),
      signal: controller.signal,
    });
  } catch (err) {
    throw new SpeakError(err?.name === "AbortError" ? "timeout" : "network");
  } finally {
    clearTimeout(timer);
  }
  if (response.status !== 200) throw new SpeakError("http", `HTTP ${response.status}`);

  let body;
  try {
    body = await response.json();
  } catch {
    throw new SpeakError("invalid_response");
  }
  if (typeof body?.audio_base64 !== "string" || !body.audio_base64) throw new SpeakError("invalid_response");
  const url = `data:${body.content_type || "audio/mpeg"};base64,${body.audio_base64}`;
  cache.set(key, url);
  return url;
}

// 테스트용
export function clearSpeechCache() {
  cache.clear();
}
