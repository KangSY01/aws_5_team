// 데모 스위치 패널 미리보기 (개발용, D). npm run dev 후 /src/features/demo-panel/preview.html 로 연다.
// App.jsx 에 붙이기 전에 패널만 따로 보고, 요청 본문에 붙는 demo 값을 확인한다.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../../styles/app.css";
import { DemoPanel, useDemoSwitch, withDemo } from "./index.js";

function Preview() {
  useDemoSwitch(); // 값이 바뀌면 아래 예시를 다시 그린다
  const body = withDemo({ plan_id: "plan-1" });
  return (
    <main className="app">
      <h1>데모 스위치 패널 미리보기</h1>
      <p>왼쪽 아래 DEMO 버튼을 눌러 보세요. POST /plan/check 요청 본문이 이렇게 바뀝니다.</p>
      <pre style={{ padding: 12, background: "#f5f5f6", borderRadius: 8 }}>{JSON.stringify(body, null, 2)}</pre>
      <DemoPanel defaultOpen />
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
);
