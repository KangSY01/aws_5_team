import { expect, it } from "vitest";
import { getTripStop, insertStopAfter, overlappingStops, reorderStops, stopDate } from "../lib/itineraryTiming.js";

const date = "2026-11-21";
const makeStop = (id, start, end, day = date) => ({
  stop_id: id,
  start: `${day}T${start}:00+09:00`,
  end: `${day}T${end}:00+09:00`,
});

it("keeps the requested start time and declines an insertion that would crowd another visit", () => {
  const anchor = makeStop("museum", "13:20", "14:50");
  const requested = [4 * 60 + 30, 16 * 60 + 30];
  expect(insertStopAfter([anchor], 0, "park", requested)[1].start).toBe(`${date}T16:30:00.000+09:00`);
  expect(insertStopAfter([anchor, makeStop("next", "17:30", "18:30")], 0, "park", requested)).toBeNull();
  expect(insertStopAfter([anchor], 0, "park", [4 * 60 + 30])).toBeNull();
});

it("uses the next scheduled visit during gaps and clears the target after the last visit", () => {
  const morning = makeStop("morning", "10:00", "11:00");
  const afternoon = makeStop("afternoon", "13:00", "14:00");
  const tomorrow = makeStop("tomorrow", "09:00", "10:00", "2026-11-22");
  const at = (time) => Date.parse(`${date}T${time}:00+09:00`);
  const stops = [tomorrow, afternoon, morning];
  expect(getTripStop(stops, at("08:00"))).toBe(morning);
  expect(getTripStop(stops, at("10:30"))).toBe(morning);
  expect(getTripStop(stops, at("11:00"))).toBe(afternoon);
  expect(getTripStop(stops, at("14:00"))).toBe(tomorrow);
  expect(getTripStop(stops, Date.parse(tomorrow.end))).toBeNull();
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
