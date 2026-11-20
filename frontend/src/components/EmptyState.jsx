import { EMPTY_MESSAGE } from "../constants/messages.js";

// 빈 일정 화면. date 가 없거나 빈 문자열이면 날짜 영역을 렌더링하지 않는다.
export default function EmptyState({ date, message = EMPTY_MESSAGE }) {
  const hasDate = typeof date === "string" && date !== "";
  return (
    <div className="empty-state">
      {hasDate && <p className="empty-state-date">{date}</p>}
      <p className="empty-state-message">{message}</p>
    </div>
  );
}
