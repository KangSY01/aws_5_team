import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import TransitLeg from "../components/TransitLeg.jsx";

it("shows walk and bus parts, line names, total minutes, and boarding stops", () => {
  const route = {
    mode: "transit", minutes: 24, source: "kakao",
    segments: [
      { mode: "WALKING", lines: [], minutes: 10, path: [] },
      { mode: "BUS", lines: ["1003", "185", "1003(심야)"], minutes: 4, path: [], from_name: "동백섬입구", to_name: "해운대해수욕장" },
      { mode: "WALKING", lines: [], minutes: 8, path: [] },
    ],
  };
  render(<TransitLeg route={route} language="ko" />);
  expect(screen.getByLabelText("다음 장소까지 이동")).toHaveTextContent("🚶도보10분🚌버스1003, 1854분🚶도보8분총 24분");
  expect(screen.getByText("동백섬입구 승차 → 해운대해수욕장 하차")).toBeVisible();
});

it("marks straight-line fallbacks as estimates and hides legs without travel", () => {
  const walk = { mode: "walk", minutes: 17, source: "straight", segments: [{ mode: "WALKING", lines: [], minutes: 17, path: [] }] };
  const { container } = render(<><TransitLeg route={walk} language="en" />
    <TransitLeg route={{ ...walk, minutes: 0 }} language="en" /></>);
  expect(screen.getByLabelText("Travel to the next stop")).toHaveTextContent(/^🚶Walk17 min\(estimate\)$/);
  expect(container.querySelectorAll(".transit-leg")).toHaveLength(1);
});
