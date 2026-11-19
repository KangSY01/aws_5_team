import {
  BASE_URL_LABEL,
  ERROR_CODE_LABEL,
  ERROR_TITLES,
  INVALID_RESPONSE_HINT,
  NETWORK_HINT,
  RETRY_LABEL,
  TIMEOUT_HINT,
} from "../constants/messages.js";

// 오류 종류별 제목과 상세 줄을 계산한다.
// 서버 message 는 문자열 그대로 React 텍스트 노드로만 출력한다.
function describeError(error, baseUrl) {
  switch (error?.kind) {
    case "network":
      return {
        title: ERROR_TITLES.network,
        lines: [`${BASE_URL_LABEL}: ${baseUrl ?? ""}`, NETWORK_HINT],
      };
    case "timeout":
      return { title: ERROR_TITLES.timeout, lines: [TIMEOUT_HINT] };
    case "http": {
      const hasBody =
        typeof error.code === "string" && typeof error.serverMessage === "string";
      if (error.status === 404 && error.code === "plan_not_found" && hasBody) {
        return { title: ERROR_TITLES.notFound, lines: [error.serverMessage] };
      }
      if (hasBody) {
        return {
          title: ERROR_TITLES.http,
          lines: [`${ERROR_CODE_LABEL}: ${error.code}`, error.serverMessage],
        };
      }
      return { title: ERROR_TITLES.http, lines: [`HTTP ${error.status}`] };
    }
    default:
      // invalid_response 및 알 수 없는 종류
      return {
        title: ERROR_TITLES.invalidResponse,
        lines: [INVALID_RESPONSE_HINT],
      };
  }
}

// 오류 화면. 모든 종류에서 role="alert" 와 활성 "다시 시도" 버튼을 가진다.
export default function ErrorState({ error, baseUrl, onRetry, copy }) {
  const { title, lines } = copy ? { title: copy.errorTitles[error.kind] ?? copy.errorTitles.invalid_response, lines: error.status ? [`HTTP ${error.status}`] : [] } : describeError(error, baseUrl);
  return (
    <div className="error-state" role="alert">
      <h2 className="error-title">{title}</h2>
      {lines.map((line, index) => (
        <p className="error-detail" key={index}>
          {line}
        </p>
      ))}
      <button type="button" className="retry-button" onClick={onRetry}>
        {copy?.retry ?? RETRY_LABEL}
      </button>
    </div>
  );
}
