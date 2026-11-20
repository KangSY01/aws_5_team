import { LOADING_MESSAGE } from "../constants/messages.js";

// 로딩 상태 화면. "다시 시도" 버튼은 두지 않는다 (Requirement 6.5).
export default function LoadingState({ message = LOADING_MESSAGE } = {}) {
  return (
    <div className="loading-state" role="status" aria-busy="true">
      {/* CSS 스피너 (스타일은 styles 에서 정의) */}
      <span className="loading-spinner" aria-hidden="true" />
      <p className="loading-message">{message}</p>
    </div>
  );
}
