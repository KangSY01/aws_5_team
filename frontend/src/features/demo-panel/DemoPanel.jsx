import { useId, useState } from "react";
import { SCENES, applyScene, setDemo } from "./demoStore.js";
import { useDemoSwitch } from "./useDemoSwitch.js";
import "./demo-panel.css";

// 발표자용 데모 스위치 패널 (D). DEMO 버튼으로 설정을 열고 닫는다.
// 발표자만 보는 화면이라 문구는 한국어다 (사용자 다국어 문구 사전에 넣지 않는다).
export default function DemoPanel({ defaultOpen = false, open: controlledOpen, onOpenChange }) {
  const demo = useDemoSwitch();
  const [localOpen, setOpen] = useState(defaultOpen);
  const open = controlledOpen ?? localOpen;
  const panelId = useId();
  const status = demo.enabled ? "켜짐" : "꺼짐";

  return (
    <div className="demo-panel">
      <button
        type="button"
        className={`demo-panel__toggle${demo.enabled ? " demo-panel__toggle--on" : ""}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => (onOpenChange ?? setOpen)(!open)}
      >
        DEMO <span className="demo-panel__summary">· {status}</span>
      </button>

      {open && (
        <section id={panelId} className="demo-panel__body" aria-label="데모 스위치">
          <label className="demo-panel__switch">
            <span>데모 스위치 켜기</span>
            <input
              type="checkbox"
              role="switch"
              checked={demo.enabled}
              onChange={(event) => setDemo({
                enabled: event.target.checked,
                now: event.target.checked ? demo.now ?? SCENES[0].now : demo.now,
              })}
            />
            <span className="demo-panel__track" aria-hidden="true" />
          </label>

          <fieldset className="demo-panel__scenes">
            <legend>장면 바로가기</legend>
            {SCENES.map((scene) => (
              <button key={scene.id} type="button" onClick={() => applyScene(scene.id)}>
                {scene.label}
              </button>
            ))}
          </fieldset>

        </section>
      )}
    </div>
  );
}
