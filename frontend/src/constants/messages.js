// UI 문구 상수 모음 (한국어).
// 후속 다국어 전환 때 교체 지점을 이 파일 하나로 두기 위해 문구를 한곳에 모은다.

// 로딩 상태 문구 (Requirement 6.1)
export const LOADING_MESSAGE = "일정을 불러오는 중";

// 빈 일정 상태 문구 (Requirement 7.1)
export const EMPTY_MESSAGE = "아직 일정이 없습니다";

// 오류 종류별 제목 (Requirement 8.1, 8.3, 8.5 및 design.md 오류 표)
export const ERROR_TITLES = {
  // kind === "network"
  network: "서버에 연결할 수 없습니다",
  // kind === "timeout"
  timeout: "응답이 지연되고 있습니다",
  // kind === "http" + 404 + code "plan_not_found"
  notFound: "일정을 찾을 수 없습니다",
  // kind === "http" (그 외 상태 코드)
  http: "요청을 처리하지 못했습니다",
  // kind === "invalid_response"
  invalidResponse: "응답 형식이 올바르지 않습니다",
};

// 오류 화면 보조 안내 문구
export const NETWORK_HINT = "로컬 서버가 실행 중인지 확인해 주세요.";
export const TIMEOUT_HINT = "10초 안에 응답을 받지 못했습니다.";
export const INVALID_RESPONSE_HINT = "서버가 예상하지 못한 형식으로 응답했습니다.";

// 오류 상세 라벨
export const BASE_URL_LABEL = "요청 주소";
export const ERROR_CODE_LABEL = "코드";

// 버튼 문구 (Requirement 2.3, 8.6)
export const RETRY_LABEL = "다시 시도";

// 고정된 일정 표시 문구 (Requirement 5.3)
export const LOCKED_LABEL = "고정";

// 장소명을 찾지 못해 place_id 로 대체했을 때의 보조 문구 (Requirement 4.6)
export const PLACE_NAME_FALLBACK_NOTE = "장소 이름을 찾을 수 없어 ID 로 표시합니다";
