import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { resolvePlaceName } from "../lib/resolvePlaceName.js";
import { recommendDemo } from "../lib/demoPlanner.js";

beforeEach(() => vi.stubEnv("VITE_API_BASE_URL", ""));

afterEach(() => {
  vi.unstubAllEnvs();
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

it("identifies an API failure during itinerary creation and includes the AWS request ID", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: "internal_error", message: "Server error" },
  }), { status: 500, headers: { "x-amzn-requestid": "test-request-id" } })));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Itinerary", exact: true }));
  await user.click(screen.getByRole("button", { name: "Get an AI itinerary" }));
  await user.click(screen.getByRole("button", { name: "Create itinerary" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("POST /chat · HTTP 500 · AWS ID test-request-id");
  expect(screen.getByRole("button", { name: "Create itinerary" })).toBeEnabled();
});

it("shows Korean names for AWS places missing Korean and preserves other language names", () => {
  const place = { place_id: "busan-citizens-park", names: { ja: "釜山市民公園" } };
  const places = new Map([[place.place_id, place]]);
  expect(resolvePlaceName(place, places, "ko").name).toBe("부산시민공원");
  expect(resolvePlaceName(place, places, "ja").name).toBe("釜山市民公園");
  place.names.ko = "서버가 제공한 한국어 이름";
  expect(resolvePlaceName(place, places, "ko").name).toBe(place.names.ko);
});

it("shows a Korean edit outcome when the API replies in English and translation is unavailable", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubEnv("VITE_TRANSLATION_ENDPOINT", "");
  vi.stubGlobal("Translator", undefined);
  const [plan, places] = await Promise.all([
    import("../mocks/sample_plan.json").then((module) => module.default),
    import("../mocks/places.json").then((module) => module.default),
  ]);
  localStorage.setItem("busannow.language", "ko");
  localStorage.setItem("busannow.course", JSON.stringify({ plan, places, session_id: "test-session" }));
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(Response.json({ plan_id: plan.plan_id, session_id: "test-session", language: "en", answer: "No escape room found.", plan_changes: [] }))
    .mockResolvedValueOnce(Response.json({ plan, places })));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "일정", exact: true }));
  await user.click(screen.getAllByRole("button", { name: /AI로 수정/ })[0]);
  await user.type(screen.getByRole("textbox"), "공포 방탈출로 바꿔줘");
  await user.click(screen.getByRole("button", { name: "전송" }));
  expect(await screen.findByText("요청한 변경을 반영하지 못했어요. 기존 일정은 그대로예요.")).toHaveAttribute("lang", "ko");
});
