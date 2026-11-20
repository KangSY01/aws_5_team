import { pick } from "./copy.js";
import "./data-notices.css";

// 지도 혼잡 범례 (D, 디자인 실험). 마커 색(여유·보통·혼잡)의 뜻과, 값이 하루 단위 추정이라는 점을 함께 적는다.
// 집중률은 일 단위라 시간대별 혼잡을 말하지 않는다 (.kiro/steering/data-rules.md).
const LEGEND = {
  ko: { calm: "여유", moderate: "보통", busy: "혼잡", note: "하루 단위 혼잡 추정 · 한국관광공사" },
  en: { calm: "Calm", moderate: "Moderate", busy: "Busy", note: "Daily crowd estimate · Korea Tourism Organization" },
  ja: { calm: "空いている", moderate: "やや混雑", busy: "混雑", note: "1日単位の混雑予測・韓国観光公社" },
  "zh-Hans": { calm: "宽松", moderate: "一般", busy: "拥挤", note: "按日拥挤预测 · 韩国观光公社" },
  "zh-Hant": { calm: "寬鬆", moderate: "一般", busy: "擁擠", note: "按日擁擠預測 · 韓國觀光公社" },
};

export default function CrowdLegend({ language }) {
  const copy = pick(LEGEND, language);
  return (
    <section className="crowd-legend" aria-label={copy.note} lang={language}>
      <ul>
        {["calm", "moderate", "busy"].map((level) => (
          <li key={level}><span className="crowd-legend__swatch" data-crowd={level} aria-hidden="true" />{copy[level]}</li>
        ))}
      </ul>
      <p>{copy.note}</p>
    </section>
  );
}

export { LEGEND as CROWD_LEGEND };
