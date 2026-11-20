import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { recommendDemo } from "../lib/demoPlanner.js";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

it.each([
  ["songdo", ["gamcheon-village", "songdo-beach", "songdo-cable-car"]],
  ["estuary", ["dadaepo-beach", "eulsukdo-eco-park", "busan-moca"]],
  ["geumjeong", ["geumjeong-east-gate", "geumgang-park", "beomeosa-temple"]],
])("uses the verified places for %s in the demo itinerary", async (region, ids) => {
  const course = await recommendDemo({ regions: [region], duration: "day", activities: [], food: "" }, "en");
  expect(course.plan.stops.map((stop) => stop.place_id)).toEqual(ids);
  expect(course.places.every((place) => Number.isFinite(place.lat) && Number.isFinite(place.lng))).toBe(true);
  expect(course.limited_places).toBe(true);
});

it.each([
  [["ocean_cafe"], "coralani"],
  [["local_cafe"], "fm-coffee-house"],
  [["cafe", "ocean_cafe"], "coralani"],
])("prioritizes the correct café for %j", async (activities, first) => {
  const course = await recommendDemo({ regions: [], duration: "half", activities, food: "" }, "en");
  expect(course.plan.stops[0].place_id).toBe(first);
});

it("matches custom text to a place or a tag and reports unmatched text", async () => {
  const result = await recommendDemo({
    regions: [], duration: "half", activities: ["ocean_cafe"], food: "",
    customActivities: ["골목 사진 찍기", "Visit FM Coffee House", "Build a snowman"],
  }, "ko");
  expect(result.places).toHaveLength(3);
  expect(result.places.map(({ place_id }) => place_id)).toEqual(expect.arrayContaining(["coralani", "fm-coffee-house", "gamcheon-village"]));
  expect(result.unmatched_activities).toEqual(["Build a snowman"]);
});

it("keeps the itinerary until an AI suggestion is applied and rejects stale suggestions", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  const user = userEvent.setup();
  const select = (name) => user.click(screen.getByRole("button", { name, exact: true }));
  expect(screen.queryByRole("button", { name: "2. Jagalchi Market" })).not.toBeInTheDocument();

  await select("Itinerary");
  await select("Get an AI itinerary");
  await select("Choose areas on the map");
  await select("Haeundae · Gijang");
  await select("Close area preview");
  await select("Nampo · Yeongdo");
  await select("Add");
  await select("Done · 1");
  await screen.findByRole("button", { name: "Remove area · Nampo · Yeongdo" });
  await select("Mural villages");
  await select("Home");
  await select("Itinerary");
  expect(screen.getByRole("button", { name: "Remove area · Nampo · Yeongdo" })).toBeVisible();
  await select("Create itinerary");
  await screen.findByRole("button", { name: "Edit with AI · Jagalchi Market" });
  const course = JSON.parse(localStorage.getItem("busannow.course")).plan;
  expect(JSON.parse(localStorage.getItem("busannow.course")).preferences.regions).toEqual(["oldtown"]);

  await select("Edit with AI · Jagalchi Market");
  expect(screen.getByText("2 · Jagalchi Market")).toBeVisible();
  await user.type(screen.getByRole("textbox"), "Try a different market");
  await select("Send");
  await screen.findByRole("button", { name: "Apply to itinerary" });
  await user.type(screen.getByRole("textbox"), "Is there another option?");
  await select("Send");
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Apply to itinerary" })).toHaveLength(2));

  expect(screen.getByRole("button", { name: "2. Jagalchi Market" })).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Apply to itinerary" })[0]);
  expect(screen.getByRole("button", { name: "2. Gukje Market" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Apply to itinerary" })).not.toBeInTheDocument();
  expect(screen.getByText("The itinerary changed. Request a new suggestion.")).toBeVisible();
  const saved = JSON.parse(localStorage.getItem("busannow.course")).plan;
  expect(saved.stops).toEqual(course.stops.map((stop, index) => index === 1
    ? { ...stop, place_id: "gukje-market" } : stop));

  await select("Itinerary");
  const stop = screen.getAllByRole("listitem")[1];
  expect(within(stop).getByRole("button", { pressed: true })).toHaveTextContent("Gukje Market");
  expect(fetchMock).not.toHaveBeenCalled();
});
