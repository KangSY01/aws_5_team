import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { resetDemo } from "../features/demo-panel/demoStore.js";

if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
}

afterEach(() => {
  cleanup();
  resetDemo();
  window.localStorage.clear();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it("runs the demo script, refreshes issue badges, locks a stop, applies a repair, and undoes it", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const makeStop = (id, place, start, end) => ({
    stop_id: id, place_id: place, start: `2026-11-28T${start}:00+09:00`, end: `2026-11-28T${end}:00+09:00`, locked: false,
  });
  const original = {
    plan_id: "demo-test", date: "2026-11-28", profile: { language: "ja" },
    stops: [makeStop("beach", "haeundae", "14:00", "15:00"), makeStop("festival", "festival", "17:30", "18:30")],
  };
  let plan = original;
  const places = [
    { place_id: "haeundae", names: { en: "Haeundae" }, lat: 35.1587, lng: 129.1604 },
    { place_id: "festival", names: { en: "Light Festival" }, lat: 35.163, lng: 129.163 },
    { place_id: "gwangalli", names: { en: "Gwangalli" }, lat: 35.1532, lng: 129.1186 },
  ];
  const checkBodies = [];
  const saves = [];
  const chatBodies = [];
  const delayBodies = [];
  const fetchMock = vi.fn(async (url, request) => {
    if (url.endsWith("/chat")) {
      chatBodies.push(JSON.parse(request.body));
      return Response.json({ plan_id: plan.plan_id, session_id: "scene", language: "ja", answer: "旅程です。" });
    }
    if (url.endsWith("/plan/check")) {
      checkBodies.push(JSON.parse(request.body));
      const [beach, festival] = plan.stops;
      const issues = [
        { issue_id: "festival", stop_id: "festival", type: "crowded", severity: festival.locked ? "low" : "high", detail: "Festival crowds" },
        { issue_id: "weather", stop_id: "beach", type: "rain", severity: "medium", detail: "Afternoon rain" },
      ];
      const repairs = {};
      if (beach.place_id === "haeundae") {
        issues.unshift({ issue_id: "beach", stop_id: "beach", type: "crowded", severity: "high", detail: "Beach crowds" });
        repairs.beach = [{ action: "replace", changes: [{ stop_id: "beach", before: beach, after: { ...beach, place_id: "gwangalli" } }] }];
      }
      return Response.json({ plan_id: plan.plan_id, issues, repairs, places });
    }
    if (url.endsWith("/delay")) {
      delayBodies.push(JSON.parse(request.body));
      return Response.json({ plan_id: plan.plan_id, repairs: [], places: [] });
    }
    if (request.method === "PUT") {
      plan = JSON.parse(request.body);
      saves.push(plan);
    }
    return Response.json({ plan, places });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  const click = (name) => fireEvent.click(screen.getByRole("button", { name }));
  click(/^DEMO/);
  click(/장면 1·2 일정·혼잡/);
  click("Itinerary");
  await screen.findByRole("button", { name: "High crowding · Caution · Haeundae" });
  expect(screen.getAllByRole("button", { name: /^High crowding/ })).toHaveLength(2);
  expect(screen.queryByText("Beach crowds")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Itinerary warning/ })).not.toBeInTheDocument();
  expect(chatBodies).toEqual([expect.objectContaining({
    message: "11月28日(土)に釜山で一日過ごしたいです。海が見える所と、夜は光の祭りに行きたいです。辛いものは苦手です。",
    profile: { language: "ja" }, demo: { now: "2026-11-28T09:00:00+09:00" },
  })]);
  expect(checkBodies.at(-1).demo.now).toBe("2026-11-28T09:00:00+09:00");
  click("Lock stop · Light Festival");
  await screen.findByRole("button", { name: "Unlock stop · Light Festival" });
  await screen.findByRole("button", { name: "High crowding · Caution · Haeundae" });
  expect(screen.queryByRole("button", { name: "High crowding · Caution · Light Festival" })).not.toBeInTheDocument();
  expect(saves.at(-1).stops[1].locked).toBe(true);
  click("High crowding · Caution · Haeundae");
  const sheet = within(screen.getByRole("dialog"));
  expect(sheet.getByText("Beach crowds")).toBeVisible();
  expect(sheet.getByText(/Gwangalli/)).toBeVisible();
  fireEvent.click(sheet.getByRole("button", { name: "Apply" }));
  const undo = await screen.findByRole("button", { name: "Undo" });
  expect(saves.at(-1).stops[0].place_id).toBe("gwangalli");
  expect(screen.queryByRole("button", { name: "High crowding · Caution · Haeundae" })).not.toBeInTheDocument();
  fireEvent.click(undo);
  await screen.findByRole("button", { name: "High crowding · Caution · Haeundae" });
  expect(saves.at(-1)).toEqual({ ...original, stops: [original.stops[0], { ...original.stops[1], locked: true }] });
  click(/장면 5 오후 비/);
  await waitFor(() => expect(checkBodies.at(-1).demo).toEqual({ now: "2026-11-28T13:00:00+09:00", weather_preset: "rain-afternoon" }));
  click(/장면 6 늦었어요/);
  click("I’m running late");
  click("View delay alternatives");
  expect(await screen.findByText("No alternatives available.")).toBeVisible();
  expect(delayBodies).toEqual([{ plan_id: plan.plan_id, delay_min: 30, demo: { now: "2026-11-28T14:00:00+09:00" } }]);
});

it("opens the offline demo course at a demo time and restores the normal course on exit", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "");
  const ordinary = {
    plan: { plan_id: "ordinary", date: "2026-11-20", stops: [
      { stop_id: "normal", place_id: "normal", start: "2026-11-20T10:00:00+09:00", end: "2026-11-20T11:30:00+09:00" },
    ] },
    places: [{ place_id: "normal", names: { en: "Ordinary stop" }, lat: 35.15, lng: 129.12 }],
  };
  localStorage.setItem("busannow.course", JSON.stringify(ordinary));
  render(<App />);
  function click(name) { fireEvent.click(screen.getByRole("button", { name })); }

  expect(screen.getByRole("button", { name: "1. Ordinary stop" })).toBeInTheDocument();
  click(/^DEMO/);
  fireEvent.click(screen.getByRole("checkbox", { name: "데모 스위치 켜기" }));
  await screen.findByRole("button", { name: "1. Huinnyeoul Culture Village" });
  expect(screen.queryByRole("button", { name: "1. Ordinary stop" })).not.toBeInTheDocument();
  click("Itinerary");
  click("Start trip");
  fireEvent.change(screen.getByLabelText("기준 시각 (한국 시각)"), { target: { value: "2026-11-28T14:30" } });
  expect(await screen.findByText("Haeundae Beach", { selector: ".trip-next strong" })).toBeVisible();
  expect(screen.getByRole("button", { name: "3. Haeundae Beach", current: true })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "데모 스위치 켜기" }));
  expect(screen.getByRole("button", { name: "1. Ordinary stop" })).toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("busannow.course"))).toEqual(ordinary);
  expect(JSON.parse(localStorage.getItem("busannow.course.demo")).plan.date).toBe("2026-11-28");
});

it("opens travel phrases independently of emergency help and sends Korean text to speech", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const fetchMock = vi.fn().mockResolvedValue(Response.json({ content_type: "audio/mpeg", audio_base64: "eA==" }));
  const play = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("Audio", class {
    play = play;
    pause() {}
  });
  render(<App />);
  const trigger = screen.getAllByRole("button", { name: "Travel Phrases", exact: true })[0];
  fireEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Useful Korean Phrases" })).toBeVisible();
  expect(document.querySelector(".emergency-dialog")).not.toHaveAttribute("open");
  expect(window.history.state?.busanEmergencyHelp).toBeUndefined();
  fireEvent.click(screen.getByRole("button", { name: /Could you make it less spicy/ }));
  const card = screen.getAllByRole("dialog", { name: "Show this to a local" }).at(-1);
  expect(within(card).getByText("덜 맵게 해 주실 수 있나요?")).toBeVisible();
  fireEvent.click(within(card).getByRole("button", { name: /Play in Korean/ }));
  await waitFor(() => expect(play).toHaveBeenCalledOnce());
  const [[url, request]] = fetchMock.mock.calls;
  expect(url).toMatch(/\/speak$/);
  expect(JSON.parse(request.body)).toEqual({ text: "덜 맵게 해 주실 수 있나요?", language: "ko" });
});
