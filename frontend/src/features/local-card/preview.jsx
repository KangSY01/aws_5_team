// 현지인 카드 미리보기 (개발용, D). npm run dev 후 /src/features/local-card/preview.html 로 연다.
// 🔊 는 VITE_API_BASE_URL(없으면 http://127.0.0.1:8000)의 POST /speak 를 부른다. 로컬 백엔드는 USE_MOCK=1 이면 샘플 mp3 를 준다.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../styles/app.css";
import { LocalCardPicker } from "./index.js";
import { LANGUAGES } from "./phrases.js";

function Preview() {
  const [language, setLanguage] = useState("ja");
  return (
    <main className="app">
      <h1>현지인에게 보여주기 카드 미리보기</h1>
      <label>
        사용자 언어{" "}
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          {LANGUAGES.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </label>
      <LocalCardPicker language={language} />
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
);
