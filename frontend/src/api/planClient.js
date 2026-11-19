// Plan_API(GET /plan/{plan_id}) 호출 클라이언트.


const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 10000;

/**
 * 오류 종류: "network" | "timeout" | "http" | "invalid_response"
 * status: HTTP 상태 코드 (kind === "http" 일 때만)
 * code / serverMessage: Error_Body 값 (형식이 맞을 때만)
 */
export class PlanClientError extends Error {
  constructor(kind, { status, code, serverMessage, message } = {}) {
    super(message ?? `Plan 요청 실패: ${kind}`);
    this.name = "PlanClientError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.serverMessage = serverMessage;
  }
}

// 비어 있지 않은 문자열이면 끝의 "/" 를 제거해 반환한다.
function normalizeBaseUrl(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return trimmed.replace(/\/+$/, "");
}

/**
 * Base_URL 계산: VITE_API_BASE_URL (공백 아닌 값) 또는 기본값.
 * 끝의 "/" 는 제거한다.
 */
export function getBaseUrl() {
  const fromEnv = normalizeBaseUrl(import.meta.env?.VITE_API_BASE_URL);
  return fromEnv ?? DEFAULT_BASE_URL;
}

function createAbortError() {
  return new DOMException("요청이 취소되었습니다.", "AbortError");
}

// Error_Body: error.code 와 error.message 가 모두 문자열일 때만 인정한다.
function parseErrorBody(body) {
  const error = body?.error;
  if (
    error !== null &&
    typeof error === "object" &&
    typeof error.code === "string" &&
    typeof error.message === "string"
  ) {
    return { code: error.code, serverMessage: error.message };
  }
  return {};
}

/**
 * 성공 시 { plan, places } 를 반환하고, 실패 시 PlanClientError 를 던진다.
 * 호출자 signal 로 취소하면 AbortError 를 그대로 던진다.
 */
async function requestJson(
  path,
  { baseUrl, signal, timeoutMs = DEFAULT_TIMEOUT_MS, request = {} } = {},
) {
  if (signal?.aborted) throw createAbortError();

  const base = normalizeBaseUrl(baseUrl) ?? getBaseUrl();
  const url = `${base}${path}`;

  // 호출자 signal 과 타임아웃을 하나의 컨트롤러로 합친다.
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort, { once: true });

  // 중단/실패 원인을 분류한다.
  const classify = (err) => {
    if (signal?.aborted) return err?.name === "AbortError" ? err : createAbortError();
    if (timedOut) return new PlanClientError("timeout", { message: "응답 시간 초과" });
    return new PlanClientError("network", { message: "네트워크 연결 실패" });
  };

  try {
    let response;
    try {
      response = await fetch(url, { ...request, signal: controller.signal });
    } catch (err) {
      throw classify(err);
    }

    if (response.status !== 200) {
      // 201, 204 등 200 이외 모든 상태는 http 오류로 처리한다.
      let details = {};
      try {
        details = parseErrorBody(await response.json());
      } catch (err) {
        if (signal?.aborted || timedOut) throw classify(err);
        // 본문 읽기/파싱 실패는 상태 코드만 담는다.
      }
      throw new PlanClientError("http", {
        status: response.status,
        message: `HTTP ${response.status}`,
        ...details,
      });
    }

    let body;
    try {
      body = await response.json();
    } catch (err) {
      if (signal?.aborted || timedOut) throw classify(err);
      throw new PlanClientError("invalid_response", {
        message: "응답이 JSON 이 아닙니다",
      });
    }

    return body;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
}


export async function fetchPlan(planId, options) {
  const body = await requestJson(`/plan/${encodeURIComponent(planId)}`, { ...options, request: { method: "GET" } });
  if (!Array.isArray(body?.plan?.stops) || !Array.isArray(body?.places)) {
    throw new PlanClientError("invalid_response");
  }
  return { plan: body.plan, places: body.places };
}

export async function sendTravelMessage(message, language, session) {
  const chat = await requestJson("/chat", {
    request: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        profile: { language },
        session_id: session?.session_id ?? null,
        plan_id: session?.plan_id ?? null,
      }),
    },
  });
  if (typeof chat?.plan_id !== "string" || !chat.plan_id) {
    throw new PlanClientError("invalid_response");
  }

  return chat;
}
