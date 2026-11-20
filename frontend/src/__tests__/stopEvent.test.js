import { describe, expect, it } from "vitest";
import { eventName, findStopEvent } from "../lib/stopEvent.js";

const festival = {
  name: "해운대 빛축제", names: { ja: "海雲台光祭り", en: "Haeundae Light Festival" },
  place_ids: ["haeundae-beach", "haeundae-market"], start: "2026-11-28T18:00:00+09:00", end: "2026-11-28T23:00:00+09:00",
};
const stop = (start, end, place_id = "haeundae-beach") => ({ place_id, start: `2026-11-28T${start}:00+09:00`, end: `2026-11-28T${end}:00+09:00` });

describe("findStopEvent", () => {
  it("labels only the visit that overlaps the festival time", () => {
    expect(findStopEvent(stop("14:30", "16:00"), [festival])).toBeNull();
    expect(findStopEvent(stop("17:30", "19:30"), [festival])).toBe(festival);
  });
  it("needs the same place and tolerates missing data", () => {
    expect(findStopEvent(stop("18:00", "19:00", "gwangalli-beach"), [festival])).toBeNull();
    expect(findStopEvent(stop("18:00", "19:00"), undefined)).toBeNull();
    expect(findStopEvent({ place_id: "haeundae-beach" }, [festival])).toBeNull();
  });
  it("uses the traveler's language with English and Korean fallbacks", () => {
    expect(eventName(festival, "ja")).toBe("海雲台光祭り");
    expect(eventName(festival, "zh-Hans")).toBe("Haeundae Light Festival");
    expect(eventName({ name: "행사" }, "ja")).toBe("행사");
    expect(eventName(null, "ja")).toBe("");
  });
});
