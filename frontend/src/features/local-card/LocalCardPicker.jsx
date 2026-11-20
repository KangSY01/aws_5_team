import { useState } from "react";
import LocalCard from "./LocalCard.jsx";
import { PHRASES, copyFor } from "./phrases.js";

// 고정 문구 목록 (D). 사용자 언어로 뜻을 보여 주고, 누르면 한국어 카드를 연다.
// 여행 중 모드의 "현지인에게 보여주기" 버튼이나 채팅 답변 아래에 붙인다 (C 가 연결).
export default function LocalCardPicker({ language = "en", speak }) {
  const copy = copyFor(language);
  const [openId, setOpenId] = useState(null);
  const phrase = PHRASES.find((p) => p.id === openId);

  return (
    <section className="local-card-picker" aria-label={copy.listTitle}>
      <h2 className="local-card-picker__title">{copy.listTitle}</h2>
      <ul className="local-card-picker__list">
        {PHRASES.map((p) => (
          <li key={p.id}>
            <button type="button" className="local-card-picker__item" onClick={() => setOpenId(p.id)}>
              <span className="local-card-picker__meaning">{p[language] ?? p.en}</span>
              <span className="local-card-picker__ko" lang="ko">{p.ko}</span>
            </button>
          </li>
        ))}
      </ul>
      {phrase && (
        <LocalCard
          textKo={phrase.ko}
          translation={phrase[language] ?? phrase.en}
          language={language}
          onClose={() => setOpenId(null)}
          speak={speak}
        />
      )}
    </section>
  );
}
