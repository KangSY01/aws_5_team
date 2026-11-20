import { useCallback, useLayoutEffect, useRef, useState } from "react";
import LocalCard from "./LocalCard.jsx";
import { PHRASES, copyFor } from "./phrases.js";

const groups = ["dining", "help"];

// 고정 문구 목록 (D). 사용자 언어로 뜻을 보여 주고, 누르면 한국어 카드를 연다.
// 여행 중 모드의 "현지인에게 보여주기" 버튼이나 채팅 답변 아래에 붙인다 (C 가 연결).
export default function LocalCardPicker({ language = "en", speak, hideTitle = false }) {
  const copy = copyFor(language);
  const [openId, setOpenId] = useState(null);
  const lastTrigger = useRef(null);
  const phrase = PHRASES.find((p) => p.id === openId);
  const goBack = useCallback(() => setOpenId(null), []);

  useLayoutEffect(() => {
    if (openId === null) lastTrigger.current?.focus({ preventScroll: true });
  }, [openId]);

  return (
    <section className="local-card-picker" aria-label={copy.listTitle}>
      {!hideTitle && <h2 className="local-card-picker__title">{copy.listTitle}</h2>}
      <div className="local-card-picker__scroll" inert={Boolean(phrase)}>
        {groups.map((group) => (
          <section key={group} className="local-card-picker__group" aria-label={copy[group]}>
            <h3>{copy[group]}</h3>
            <ul className="local-card-picker__list">
              {PHRASES.filter((p) => p.group === group).map((p) => (
                <li key={p.id}>
                  <button type="button" className="local-card-picker__item" onClick={(event) => {
                    lastTrigger.current = event.currentTarget;
                    setOpenId(p.id);
                  }}>
                    <span className="local-card-picker__texts">
                      {language !== "ko" && <span className="local-card-picker__meaning">{p[language] ?? p.en}</span>}
                      <span className="local-card-picker__ko" data-secondary={language !== "ko"} lang="ko">{p.ko}</span>
                    </span>
                    <span className="local-card-picker__chevron" aria-hidden="true">›</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {phrase && (
        <LocalCard
          textKo={phrase.ko}
          translation={language === "ko" ? undefined : phrase[language] ?? phrase.en}
          language={language}
          onClose={goBack}
          returnLabel={copy.back}
          speak={speak}
        />
      )}
    </section>
  );
}
