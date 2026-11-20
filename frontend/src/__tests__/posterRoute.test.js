import { expect, it } from "vitest";
import { posterRoute } from "../features/trip-poster/posterRoute.js";

const a = [129.12, 35.15];
const b = [129.16, 35.16];
const c = [129.20, 35.18];
const bend = [129.14, 35.17];
const stops = [a, b, c].map((coordinate) => ({ coordinate }));
const latLng = ([lng, lat]) => [lat, lng];

it("orients saved geometry in visit order and connects missing legs", () => {
  expect(posterRoute(stops, [[b, bend, a].map(latLng)])).toEqual([
    { points: [a, bend, b], saved: true },
    { points: [b, c], saved: false },
  ]);
});

it("connects each pair when saved geometry is unavailable or unrelated", () => {
  expect(posterRoute(stops, [[[35.1, 129.01], [35.13, 129.03]]])).toEqual([
    { points: [a, b], saved: false },
    { points: [b, c], saved: false },
  ]);
});
