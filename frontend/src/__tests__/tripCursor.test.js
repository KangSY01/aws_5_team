import { expect, it } from "vitest";
import { tripCursorY } from "../lib/tripCursor.js";

const stops = [
  { start: "2026-11-28T10:00:00+09:00", end: "2026-11-28T11:00:00+09:00" },
  { start: "2026-11-28T12:00:00+09:00", end: "2026-11-28T13:00:00+09:00" },
];
const at = (time) => Date.parse("2026-11-28T" + time + ":00+09:00");

it("keeps the cursor on a stop while staying and moves it between stops by travel time", () => {
  expect(tripCursorY(stops, [20, 120], at("09:00"))).toBe(20);
  expect(tripCursorY(stops, [20, 120], at("10:30"))).toBe(20);
  expect(tripCursorY(stops, [20, 120], at("11:30"))).toBe(70);
  expect(tripCursorY(stops, [20, 120], at("12:15"))).toBe(120);
  expect(tripCursorY(stops, [20, 120], at("14:00"))).toBe(120);
  expect(tripCursorY(stops, [20], at("11:30"))).toBeNull();
});
