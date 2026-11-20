import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles/app.css";
import "./styles/skin.css"; // 디자인 시험 (design/giljabi-ui). 지우면 원래 디자인

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
