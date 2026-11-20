import { useEffect, useRef, useState } from "react";
import { copyFor } from "./phrases.js";
import { fetchSpeech } from "./speakClient.js";
import "./local-card.css";

// 현지인에게 보여주기 카드 (D, 장면 4). 한국어 문장을 화면 가득 크게 보여 주고, 🔊 로 한국어 음성(/speak)을 들려준다.
// props
// - textKo: 카드에 보일 한국어 문장 (필수)
// - translation: 사용자 언어로 된 뜻 (선택)
// - language: 사용자 언어 (en / ja / zh-Hans / zh-Hant). 버튼·안내 문구에 쓴다
// - onClose: 닫기
// - speak: 테스트·미리보기용으로 음성 함수를 바꿔 끼운다 (기본 fetchSpeech)
export default function LocalCard({ textKo, translation, language = "en", onClose, speak = fetchSpeech }) {
  const copy = copyFor(language);
  const [status, setStatus] = useState("idle"); // idle | loading | playing | error
  const audioRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      audioRef.current?.pause();
    };
  }, [onClose]);

  async function play() {
    if (status === "loading") return;
    setStatus("loading");
    try {
      const url = await speak(textKo, "ko");
      audioRef.current?.pause();
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setStatus("idle");
      await audio.play();
      setStatus("playing");
    } catch {
      setStatus("error");
    }
  }

  const label = { idle: copy.speak, error: copy.speak, loading: copy.loading, playing: copy.speaking }[status];

  return (
    <div className="local-card" role="dialog" aria-modal="true" aria-label={copy.title}>
      <div className="local-card__inner">
        <p className="local-card__title">{copy.title}</p>
        <p className="local-card__ko" lang="ko">{textKo}</p>
        {translation && (
          <p className="local-card__meaning">
            <span className="local-card__meaning-label">{copy.meaning}</span> {translation}
          </p>
        )}
        <div className="local-card__actions">
          <button type="button" className="local-card__speak" onClick={play} aria-busy={status === "loading"}>
            🔊 {label}
          </button>
          <button type="button" className="local-card__close" onClick={onClose} ref={closeRef}>
            {copy.close}
          </button>
        </div>
        {status === "error" && <p className="local-card__error" role="alert">{copy.speakError}</p>}
      </div>
    </div>
  );
}
