import { useId, useState } from "react";
import {
  SCENES,
  WEATHER_PRESETS,
  applyScene,
  fromLocalInput,
  resetDemo,
  setDemo,
  toLocalInput,
} from "./demoStore.js";
import { useDemoSwitch } from "./useDemoSwitch.js";
import "./demo-panel.css";

// 발표자용 데모 스위치 패널 (D). 화면 구석의 DEMO 버튼으로 열고 닫는다.
// 발표자만 보는 화면이라 문구는 한국어다 (사용자 다국어 문구 사전에 넣지 않는다).
function formatNow(iso) {
  const local = toLocalInput(iso);
  return local ? `${local.slice(5, 10).replace("-", "/")} ${local.slice(11, 16)}` : "현재 시각";
}

function presetLabel(id) {
  return WEATHER_PRESETS.find((p) => p.id === id)?.label ?? "실제 예보";
}

export default function DemoPanel({ defaultOpen = false }) {
  const demo = useDemoSwitch();
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const summary = demo.enabled ? `${formatNow(demo.now)} · ${presetLabel(demo.weatherPreset)}` : "꺼짐";

  return (
    <div className="demo-panel">
      <button
        type="button"
        className={`demo-panel__toggle${demo.enabled ? " demo-panel__toggle--on" : ""}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        DEMO <span className="demo-panel__summary">{summary}</span>
      </button>

      {open && (
        <section id={panelId} className="demo-panel__body" aria-label="데모 스위치">
          <label className="demo-panel__row demo-panel__switch">
            <input
              type="checkbox"
              checked={demo.enabled}
              onChange={(e) => setDemo({ enabled: e.target.checked })}
            />
            <span>데모 스위치 켜기</span>
          </label>

          <fieldset className="demo-panel__scenes">
            <legend>장면 바로가기</legend>
            {SCENES.map((scene) => (
              <button key={scene.id} type="button" onClick={() => applyScene(scene.id)}>
                {scene.label}
              </button>
            ))}
          </fieldset>

          <label className="demo-panel__row">
            <span>기준 시각 (한국 시각)</span>
            <input
              type="datetime-local"
              value={toLocalInput(demo.now)}
              onChange={(e) => setDemo({ now: fromLocalInput(e.target.value) })}
            />
          </label>

          <label className="demo-panel__row">
            <span>날씨</span>
            <select
              value={demo.weatherPreset ?? ""}
              onChange={(e) => setDemo({ weatherPreset: e.target.value || null })}
            >
              {WEATHER_PRESETS.map((p) => (
                <option key={p.id ?? "none"} value={p.id ?? ""}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <p className="demo-panel__note">
            켜져 있으면 일정 생성·점검·늦었어요 요청에 이 시각과 날씨를 넣습니다. 시연용 값이라고 발표에서 밝힙니다.
          </p>
          <button type="button" className="demo-panel__reset" onClick={resetDemo}>
            초기화
          </button>
        </section>
      )}
    </div>
  );
}
