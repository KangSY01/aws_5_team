import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App.jsx";

// 테스트 환경(Vitest + RTL + jsdom) 구성이 동작하는지 확인하는 스모크 테스트
describe("App 뼈대", () => {
  it("제목 문구를 렌더링한다", () => {
    render(<App />);
    expect(screen.getByText("부산 여행 일정")).toBeInTheDocument();
  });
});
