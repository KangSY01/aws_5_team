import { PlanClientError, requestJson } from "./planClient.js";

// 두 지점 사이 실제 이동 경로 (GET /route). 도보는 OSM, 대중교통은 카카오 노선 좌표.
// 응답: { mode: "walk"|"transit", minutes, source: "osm"|"kakao"|"straight", segments: [{ mode, lines, minutes, path: [[lat, lng], ...] }] }
export async function fetchRoute(from, to, signal) {
  const query = new URLSearchParams({ from: from.join(","), to: to.join(",") });
  const result = await requestJson("/route?" + query, { signal, timeoutMs: 15000 });
  if (!Array.isArray(result?.segments) || !result.segments.every((s) => Array.isArray(s.path) && s.path.length >= 2)) {
    throw new PlanClientError("invalid_response");
  }
  return result;
}
