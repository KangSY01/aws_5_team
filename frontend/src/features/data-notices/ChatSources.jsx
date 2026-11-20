import { SOURCES_LABEL, pick, providerNames } from "./copy.js";
import "./data-notices.css";

// 채팅 답변 아래 출처 한 줄 (D). 공공데이터를 보여 줄 때 출처를 함께 표기한다 (.kiro/steering/data-rules.md).
// 보여 줄 기관이 없으면 아무것도 그리지 않는다.
export default function ChatSources({ sources, language }) {
  const names = providerNames(sources, language);
  if (!names.length) return null;
  return (
    <p className="chat-sources" lang={language}>
      <span className="chat-sources__label">{pick(SOURCES_LABEL, language)}</span> {names.join(" · ")}
    </p>
  );
}
