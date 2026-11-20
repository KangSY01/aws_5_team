import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import TripProgress from "../components/TripProgress.jsx";

const stops = [
  { stop_id: "a", start: "2026-11-28T10:00:00+09:00", end: "2026-11-28T11:30:00+09:00" },
  { stop_id: "b", start: "2026-11-28T12:00:00+09:00", end: "2026-11-28T13:00:00+09:00" },
  { stop_id: "c", start: "2026-11-28T14:30:00+09:00", end: "2026-11-28T16:00:00+09:00" },
];
const time = (iso) => iso.slice(11, 16);

it("counts finished stops and shows the next stop with its start time", () => {
  render(<TripProgress stops={stops} now={Date.parse("2026-11-28T11:45:00+09:00")} current={stops[1]}
    currentName="Rodeo Street" language="en" formatTime={time} />);
  expect(screen.getByText("1 of 3 stops done")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  expect(screen.getByText("Next").parentElement).toHaveTextContent("Next Rodeo Street 12:00");
});

it("shows the current stop while staying and a finished message at the end", () => {
  const { rerender } = render(<TripProgress stops={stops} now={Date.parse("2026-11-28T12:30:00+09:00")} current={stops[1]}
    currentName="Rodeo Street" language="ko" formatTime={time} />);
  expect(screen.getByText("3곳 중 1곳 완료")).toBeVisible();
  expect(screen.getByText("지금").parentElement).toHaveTextContent("지금 Rodeo Street");
  rerender(<TripProgress stops={stops} now={Date.parse("2026-11-28T17:00:00+09:00")} current={null} language="ko" formatTime={time} />);
  expect(screen.getByText("모든 일정을 마쳤어요")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
});
