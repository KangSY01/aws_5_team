import { expect, it } from "vitest";
import { overlappingStops, reorderStops, stopDate } from "../lib/itineraryTiming.js";

const date = "2026-11-21";
const makeStop = (id, start, end, day = date) => ({
  stop_id: id,
  start: `${day}T${start}:00+09:00`,
  end: `${day}T${end}:00+09:00`,
});

it("reuses the affected start slots and keeps the duration attached to each stop", () => {
  const stops = [
    makeStop("a", "09:00", "09:30"),
    makeStop("b", "10:00", "10:15"),
    makeStop("c", "10:30", "12:00"),
    makeStop("d", "12:00", "12:30"),
  ];

  const result = reorderStops(stops, 2, 1);
  expect(result.map((stop) => stop.stop_id)).toEqual(["a", "c", "b", "d"]);
  expect(result.map((stop) => stop.start)).toEqual(stops.map((stop) => stop.start));
  expect(Date.parse(result[1].end) - Date.parse(result[1].start)).toBe(90 * 60_000);
  expect(Date.parse(result[2].end) - Date.parse(result[2].start)).toBe(15 * 60_000);
  expect(result[0]).toBe(stops[0]);
  expect(result[3]).toBe(stops[3]);
  expect(overlappingStops(result)).toEqual(new Set([1, 2]));
});

it("uses Seoul calendar days and preserves fixed appointments", () => {
  const stops = [
    { stop_id: "a", start: "2026-11-20T16:00:00Z", end: "2026-11-20T17:00:00Z" },
    makeStop("b", "03:00", "04:00"),
    { ...makeStop("fixed", "04:00", "05:00"), locked: true },
    makeStop("next-day", "01:00", "02:00", "2026-11-22"),
  ];
  expect(stopDate(stops[0].start)).toBe(date);
  expect(overlappingStops(stops).size).toBe(0);
  expect(reorderStops(stops, 0, 1)[0].stop_id).toBe("b");
  expect(reorderStops(stops, 0, 2)).toBe(stops);
  expect(reorderStops(stops, 1, 3)).toBe(stops);
  expect(reorderStops(stops.slice(0, 2).concat(stops[3]), 1, 2)[1].stop_id).toBe("b");
});
