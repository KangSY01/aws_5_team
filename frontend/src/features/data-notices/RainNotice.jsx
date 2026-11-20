import { useState } from "react";
import { useDemoSwitch } from "../demo-panel/useDemoSwitch.js";
import { RAIN_COPY, RAIN_PRESETS, pick } from "./copy.js";
import "./data-notices.css";

// 비 예보 배너 (D, 데모 장면 5). 지도 상단에 붙인다.
// 데모 스위치가 켜져 있고 날씨가 rain-afternoon 일 때만 보인다. 데모를 끄거나 다른 날씨로 바꾸면 숨는다.
// 닫으면 같은 데모 설정에서는 다시 띄우지 않고, 날씨나 데모 상태가 바뀌면 다시 띄운다.
//
// props
// - language: "ko" | "en" | "ja" | "zh-Hans" | "zh-Hant" (필수)
// - placeName: 비가 걸리는 장소 이름 (선택). 있으면 "○○ 방문 시간에" 로 말한다
// - onOpen: "대안 보기" 를 눌렀을 때 (선택). 없으면 버튼을 그리지 않는다
// - disabled: "대안 보기" 버튼 비활성 (선택, 요청 중일 때)
export default function RainNotice({ language, placeName, onOpen, disabled = false }) {
  const demo = useDemoSwitch();
  const preset = demo.enabled ? RAIN_PRESETS[demo.weatherPreset] : undefined;
  const settingKey = `${demo.enabled}:${demo.weatherPreset}`;
  const [dismissedKey, setDismissedKey] = useState(null);
  if (!preset || dismissedKey === settingKey) return null;

  const copy = pick(RAIN_COPY, language);
  return (
    <section className="rain-notice" role="status" aria-label={copy.title} lang={language}>
      <div className="rain-notice__text">
        <strong>{copy.title}</strong>
        <span>{copy.detail(`${preset.start}–${preset.end}`, placeName)}</span>
      </div>
      {onOpen && (
        <button type="button" className="rain-notice__open" aria-haspopup="dialog" disabled={disabled} onClick={onOpen}>
          {copy.open}
        </button>
      )}
      <button type="button" className="rain-notice__close" aria-label={copy.close} onClick={() => setDismissedKey(settingKey)}>
        ×
      </button>
    </section>
  );
}
