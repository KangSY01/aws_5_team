// 출처 표시·비 예보 배너 미리보기 (개발용, D). npm run dev 후 /src/features/data-notices/preview.html 로 연다.
// 오른쪽 아래 DEMO 패널에서 데모를 켜고 날씨를 "11/28 13~15시 비"로 고르면 배너가 나온다.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../styles/app.css";
import "../../components/travel-preview.css";
import { DemoPanel } from "../demo-panel";
import { ChatSources, RainNotice } from "./index.js";

const LANGUAGES = ["ja", "ko", "en", "zh-Hans", "zh-Hant"];

// 배포 API 응답에서 본 sources 모양 그대로 (장면 7 귀가, 장면 1 일정, 출처 없음)
const SAMPLES = {
  "장면 7 귀가": [
    { tool: "get_events", id: "2026-11-28", title: "해운대 빛축제" },
    { tool: "get_return_options", id: "2026-11-28:Haeundae>Seomyeon", title: "Haeundae → Seomyeon" },
  ],
  "일정·날씨": [
    { tool: "search_places", id: "haeundae-beach", title: "Haeundae Beach" },
    { tool: "get_crowd", id: "haeundae-beach", title: "Haeundae Beach" },
    { tool: "get_weather", id: "2026-11-28", title: "weather" },
  ],
  "출처 없음": [{ tool: "create_plan", id: "plan-x", title: "plan" }],
};

function Preview() {
  const [language, setLanguage] = useState("ja");
  const [sample, setSample] = useState("장면 7 귀가");
  const [withPlace, setWithPlace] = useState(true);
  const [opened, setOpened] = useState(0);

  return (
    <main className="travel-preview" lang={language} style={{ position: "static", minHeight: "100dvh", padding: 16, display: "grid", gap: 24, alignContent: "start", background: "var(--color-bg)", color: "var(--color-text)" }}>
      <h1 style={{ margin: 0, fontSize: "1.2rem" }}>출처 표시·비 예보 배너 미리보기</h1>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <label>언어{" "}
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label>sources 예시{" "}
          <select value={sample} onChange={(e) => setSample(e.target.value)}>
            {Object.keys(SAMPLES).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label><input type="checkbox" checked={withPlace} onChange={(e) => setWithPlace(e.target.checked)} /> 배너에 장소 이름 넣기</label>
      </div>

      <section>
        <h2 style={{ fontSize: "1rem" }}>① 지도 상단 비 예보 배너</h2>
        <p style={{ fontSize: ".85rem", color: "var(--color-muted)" }}>오른쪽 아래 DEMO → 데모 스위치 켜기 → 날씨 "11/28 13~15시 비". 끄거나 다른 날씨면 사라집니다.</p>
        <div style={{ minHeight: 72, padding: 12, borderRadius: 14, background: "repeating-linear-gradient(45deg, var(--color-surface) 0 12px, var(--color-bg) 12px 24px)" }}>
          <RainNotice language={language} placeName={withPlace ? "海雲台海水浴場" : undefined} onOpen={() => setOpened((n) => n + 1)} />
        </div>
        {opened > 0 && <p role="status" style={{ fontSize: ".85rem" }}>"대안 보기" 클릭 {opened}회 (실제 앱에서는 대안 시트가 열림)</p>}
      </section>

      <section>
        <h2 style={{ fontSize: "1rem" }}>② 채팅 답변 아래 출처</h2>
        <div className="chat-messages" role="log" style={{ display: "grid", gap: 10, maxWidth: 420 }}>
          <p className="chat-bubble" data-role="user">23時ごろ帰ります。地下鉄、混みますか？</p>
          <p className="chat-bubble" data-role="assistant">海雲台駅は22時30分から混雑が見込まれます。中洞駅まで歩くと約51分で西面に着きます。</p>
          <ChatSources sources={SAMPLES[sample]} language={language} />
        </div>
      </section>

      <DemoPanel />
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
);
