import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { resetDemo } from "../features/demo-panel/demoStore.js";

beforeEach(() => localStorage.setItem("busannow.traveler-profile", "{}"));

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
      const beach = plan.stops.find((stop) => stop.stop_id === "beach");
      const festival = plan.stops.find((stop) => stop.stop_id === "festival");
      const issues = [
        { issue_id: "festival", stop_id: "festival", type: "crowded", severity: festival.locked ? "low" : "high", detail: "Festival crowds" },
        { issue_id: "weather", stop_id: "beach", type: "rain", severity: "medium", detail: "Afternoon rain" },
      ];
      const repairs = {};
      if (beach?.place_id === "haeundae") {
        issues.unshift({ issue_id: "beach", stop_id: "beach", type: "crowded", severity: "high", detail: "Beach crowds" });
        repairs.beach = [{ action: "replace", changes: [{ stop_id: "beach", before: beach, after: { ...beach, place_id: "gwangalli" } }] }];
        if (checkBodies.at(-1).demo?.weather_preset === "rain-afternoon") {
          repairs.weather = [{ action: "move_time", changes: [{ stop_id: "beach", before: beach, after: {
            ...beach, start: "2026-11-28T15:00:00+09:00", end: "2026-11-28T16:00:00+09:00",
          } }] }];
        }
      }
      return Response.json({ plan_id: plan.plan_id, issues, repairs, places });
    }
    if (url.endsWith("/delay")) {
      const body = JSON.parse(request.body);
      delayBodies.push(body);
      const beach = plan.stops.find((stop) => stop.stop_id === "beach");
      const repairs = body.delay_min === 42 && beach ? [
        { action: "move_time", changes: [{ stop_id: beach.stop_id, before: beach, after: {
          ...beach, start: "2026-11-28T14:42:00+09:00", end: "2026-11-28T15:42:00+09:00",
        } }] },
        { action: "remove", changes: [{ stop_id: beach.stop_id, before: beach, after: null }] },
      ] : [];
      return Response.json({ plan_id: plan.plan_id, repairs, places: [] });
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
  await screen.findByRole("button", { name: "High crowding · Haeundae" });
  const badges = screen.getAllByRole("button", { name: /^High crowding/ });
  expect(badges).toHaveLength(2);
  for (const badge of badges) {
    expect(badge.closest(".stop-row")?.querySelector(".stop-item__name")).toHaveTextContent(badge.getAttribute("aria-label").split(" · ")[1]);
    expect(badge.getAttribute("aria-description")).toMatch(/\d{2}:\d{2} – \d{2}:\d{2}/);
  }
  expect(screen.queryByText("Beach crowds")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Itinerary warning/ })).not.toBeInTheDocument();
  expect(chatBodies).toEqual([expect.objectContaining({
    message: "11月28日(土)に釜山で一日過ごしたいです。海が見える所と、夜は光の祭りに行きたいです。辛いものは苦手です。",
    profile: { language: "ja" }, demo: { now: "2026-11-28T09:00:00+09:00" },
  })]);
  expect(checkBodies.at(-1).demo.now).toBe("2026-11-28T09:00:00+09:00");
  await waitFor(() => expect(screen.getByRole("button", { name: "Check itinerary", exact: true })).toBeEnabled());
  click("Check itinerary");
  const manualResult = await screen.findByRole("button", { name: "Haeundae · High crowding · View alternatives" });
  fireEvent.click(manualResult);
  const manualDialog = within(screen.getByRole("dialog"));
  expect(manualDialog.getByText("Beach crowds")).toBeVisible();
  fireEvent.click(manualDialog.getByRole("button", { name: "Close alternatives" }));
  click("Lock stop · Light Festival");
  await screen.findByRole("button", { name: "Unlock stop · Light Festival" });
  await screen.findByRole("button", { name: "High crowding · Haeundae" });
  expect(screen.queryByRole("button", { name: "High crowding · Light Festival" })).not.toBeInTheDocument();
  expect(saves.at(-1).stops[1].locked).toBe(true);
  click("High crowding · Haeundae");
  const sheet = within(screen.getByRole("dialog"));
  expect(sheet.getByText("Beach crowds")).toBeVisible();
  const candidate = sheet.getByRole("button", { name: "Gwangalli", expanded: false });
  expect(sheet.queryByRole("button", { name: "Switch to Gwangalli" })).not.toBeInTheDocument();
  const savedBeforePreview = saves.length;
  fireEvent.click(candidate);
  expect(candidate).toHaveAttribute("aria-expanded", "true");
  expect(sheet.getByRole("link", { name: "Place details" })).toBeVisible();
  expect(saves).toHaveLength(savedBeforePreview);
  fireEvent.click(candidate);
  expect(candidate).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(candidate);
  const switchButton = sheet.getByRole("button", { name: "Switch to Gwangalli" });
  expect(switchButton).toHaveTextContent("Switch here");
  fireEvent.click(switchButton);
  const undo = await screen.findByRole("button", { name: "Undo" });
  expect(saves.at(-1).stops[0].place_id).toBe("gwangalli");
  expect(screen.queryByRole("button", { name: "High crowding · Haeundae" })).not.toBeInTheDocument();
  fireEvent.click(undo);
  await screen.findByRole("button", { name: "High crowding · Haeundae" });
  expect(saves.at(-1)).toEqual({ ...original, stops: [original.stops[0], { ...original.stops[1], locked: true }] });
  click(/장면 5 오후 비/);
  await waitFor(() => expect(checkBodies.at(-1).demo).toEqual({ now: "2026-11-28T13:00:00+09:00", weather_preset: "rain-afternoon" }));
  click("Home");
  const rainButton = await screen.findByRole("button", { name: "See options", exact: true });
  expect(rainButton.closest(".rain-notice")).toHaveTextContent("Haeundae");
  fireEvent.click(rainButton);
  const rainDialog = within(screen.getByRole("dialog"));
  expect(rainDialog.getByText("Afternoon rain")).toBeVisible();
  expect(rainDialog.getByText("03:00 PM–04:00 PM")).toBeVisible();
  fireEvent.click(rainDialog.getByRole("button", { name: "Close alternatives" }));
  click(/장면 6 늦었어요/);
  expect(screen.queryByRole("button", { name: "See options", exact: true })).not.toBeInTheDocument();
  click("Itinerary");
  expect(screen.queryByRole("button", { name: "I’m running late" })).not.toBeInTheDocument();
  click("Start trip");
  expect(screen.queryByRole("button", { name: "I’m running late" })).not.toBeInTheDocument();
  click("Itinerary");
  expect(screen.getByRole("button", { name: "I’m running late" }).closest(".chat-heading")).toBeInTheDocument();
  click("I’m running late");
  expect(screen.getByRole("button", { name: "30 min", pressed: true })).toBeVisible();
  click("20 min");
  click("View delay alternatives");
  expect(await screen.findByText("No alternatives available.")).toBeVisible();
  expect(delayBodies).toEqual([{ plan_id: plan.plan_id, delay_min: 20, demo: { now: "2026-11-28T14:00:00+09:00" } }]);
  click("Close alternatives");
  click("I’m running late");
  click("Enter minutes");
  const input = screen.getByRole("textbox", { name: "Delay in minutes" });
  expect(input).toHaveAttribute("inputmode", "numeric");
  fireEvent.change(input, { target: { value: "241" } });
  click("View delay alternatives");
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a whole number from 1 to 240 minutes.");
  expect(delayBodies).toHaveLength(1);
  fireEvent.change(input, { target: { value: "42" } });
  click("View delay alternatives");
  const delayDialog = within(await screen.findByRole("dialog", { name: "Delay alternatives" }));
  expect(delayDialog.getAllByText("Haeundae", { exact: true })).toHaveLength(1);
  expect(delayDialog.getByText("14:00–15:00")).toBeVisible();
  expect(delayDialog.getByText("14:42–15:42")).toBeVisible();
  expect(delayDialog.getByRole("heading", { name: "Remove from itinerary" })).toBeVisible();
  expect(delayBodies.at(-1).delay_min).toBe(42);
  fireEvent.click(delayDialog.getByRole("button", { name: "Apply change" }));
  await screen.findByRole("button", { name: "Undo" });
  expect(saves.at(-1).stops[0].start).toContain("T14:42:");
  expect(saves.at(-1).stops[1].locked).toBe(true);
  click("Undo");
  await waitFor(() => expect(saves.at(-1).stops[0].start).toContain("T14:00:"));
  click("I’m running late");
  click("Enter minutes");
  fireEvent.change(screen.getByRole("textbox", { name: "Delay in minutes" }), { target: { value: "42" } });
  click("View delay alternatives");
  const remove = within(await screen.findByRole("dialog", { name: "Delay alternatives" }));
  fireEvent.click(remove.getByRole("button", { name: "Remove" }));
  await screen.findByRole("button", { name: "Undo" });
  expect(saves.at(-1).stops.map((stop) => stop.stop_id)).toEqual(["festival"]);
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
  vi.stubGlobal("fetch", (url, request) => String(url).includes("/events?")
    ? Promise.resolve(Response.json({ date: String(url).split("=").at(-1), events: [] }))
    : fetchMock(url, request));
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

it("refreshes a previously saved demo itinerary when the demo is opened again", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const date = "2026-11-28";
  const stop = { stop_id: "beach", place_id: "beach", start: date + "T14:30:00+09:00", end: date + "T16:00:00+09:00", locked: false };
  const places = [{ place_id: "beach", names: { en: "Updated demo beach" }, lat: 35.16, lng: 129.16 }];
  const plan = { plan_id: "fresh-demo", date, profile: { language: "ja" }, stops: [stop] };
  localStorage.setItem("busannow.course.demo", JSON.stringify({ plan: { ...plan, plan_id: "old-demo" },
    places: [{ ...places[0], names: { en: "Old demo beach" } }], session_id: "old-session" }));
  const requests = vi.fn(async (url, request) => {
    if (url.endsWith("/chat")) return Response.json({ plan_id: plan.plan_id, session_id: "new-session", language: "ja", answer: "旅程です。" });
    if (url.endsWith("/plan/check")) {
      return Response.json({ plan_id: JSON.parse(request.body).plan_id, places: [], issues: [], repairs: {} });
    }
    return Response.json({ plan, places });
  });
  vi.stubGlobal("fetch", requests);
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /^DEMO/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: "데모 스위치 켜기" }));
  await screen.findByRole("button", { name: "1. Updated demo beach" });
  expect(JSON.parse(localStorage.getItem("busannow.course.demo")).plan.plan_id).toBe("fresh-demo");
  expect(requests.mock.calls.filter(([url]) => url.endsWith("/chat"))).toHaveLength(1);
});
