import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

it("opens general AI chat without an itinerary and continues the same conversation", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ session_id: "general", plan_id: "chat-plan", language: "en", answer: "Try Gwangalli Beach." })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ session_id: "general", plan_id: "chat-plan", language: "en", answer: "An evening walk is an option." })));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));

  function send(message) {
    fireEvent.change(screen.getByRole("textbox"), { target: { value: message } });
    const button = screen.getByRole("button", { name: "Send" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
  }

  send("Where can I see the sea?");
  expect(await screen.findByText("Try Gwangalli Beach.")).toBeVisible();
  send("What about the evening?");
  expect(await screen.findByText("An evening walk is an option.")).toBeVisible();
  expect(fetchMock.mock.calls.map(([, request]) => JSON.parse(request.body))).toEqual([
    expect.objectContaining({ message: "Where can I see the sea?", session_id: null, plan_id: null }),
    expect.objectContaining({ message: "What about the evening?", session_id: "general", plan_id: "chat-plan" }),
  ]);
  expect(localStorage.getItem("busannow.course")).toBeNull();
});

it("answers a known landmark question in demo chat without a selected stop", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Tell me about Gwangan Bridge" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText(/This suspension bridge spans the water off Gwangalli/)).toBeVisible();
});

it.each([
  ["demo edit", false, true, "이 뒤에 시민공원 가고 싶어 추가해줘", "15:20", "16:05"],
  ["API edit", true, true, "4시 반부터 시민공원 가고 싶어 뒤의 일정에 추가해줘", "16:30", "17:15"],
  ["general chat", true, false, "4시 반에 시민공원 가고 싶어 일정에 추가해줘", "16:30", "17:15"],
  ["general chat with a conflict", true, false, "4시 반에 시민공원 가고 싶어 일정에 추가해줘", "16:50", "17:35", true],
])("adds Citizens Park after the museum and preserves the original visits (%s)", async (_mode, live, anchored, message, start, end, conflict) => {
  const stops = [
    { stop_id: "museum", place_id: "busan-museum", start: "2026-11-21T13:20:00+09:00", end: "2026-11-21T14:50:00+09:00", locked: false },
    { stop_id: "beach", place_id: "gwangalli", start: "2026-11-21T18:00:00+09:00", end: "2026-11-21T19:00:00+09:00", locked: false },
  ];
  if (conflict) {
    stops[0].end = "2026-11-21T16:20:00+09:00";
    stops[1].start = "2026-11-21T18:10:00+09:00";
  }
  const places = [
    { place_id: "busan-museum", names: { ko: "부산박물관" }, lat: 35.13, lng: 129.09 },
    { place_id: "gwangalli", names: { ko: "광안리" }, lat: 35.15, lng: 129.12 },
  ];
  const plan = { plan_id: "add-park", date: "2026-11-21", profile: { language: "en" }, stops };
  const fetchMock = vi.fn(async (url, request) => new Response(JSON.stringify(String(url).endsWith("/plan/check")
    ? { plan_id: plan.plan_id, issues: [], repairs: {}, places }
    : { plan: JSON.parse(request.body), places })));
  const putCalls = () => fetchMock.mock.calls.filter(([, request]) => request.method === "PUT");
  if (live) {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    vi.stubGlobal("fetch", fetchMock);
  }
  localStorage.setItem("busannow.language", "ko");
  localStorage.setItem("busannow.course", JSON.stringify({ plan, places, ...(live ? { session_id: "session-1" } : {}) }));
  render(<App />);
  if (anchored) {
    fireEvent.click(screen.getByRole("button", { name: "일정", exact: true }));
    fireEvent.click(screen.getByRole("button", { name: "AI로 수정 · 부산박물관" }));
  } else {
    fireEvent.click(screen.getByRole("button", { name: "채팅", exact: true }));
  }
  fireEvent.change(screen.getByRole("textbox"), { target: { value: message } });
  fireEvent.click(screen.getByRole("button", { name: "전송" }));

  const card = within(await screen.findByRole("article"));
  expect(card.getByRole("heading", { name: "부산시민공원" })).toBeVisible();
  expect(card.getByLabelText("시작 시간")).toHaveValue(start);
  expect(card.getByLabelText("종료 시간")).toHaveValue(end);
  if (conflict) expect(card.getByText(/다른 가능한 시간/)).toBeVisible();
  expect(putCalls()).toHaveLength(0);
  expect(JSON.parse(localStorage.getItem("busannow.course")).plan.stops).toEqual(stops);
  const confirmedEnd = conflict ? "17:40" : end;
  if (conflict) fireEvent.change(card.getByLabelText("종료 시간"), { target: { value: confirmedEnd } });
  fireEvent.click(card.getByRole("button", { name: "확인하고 일정에 추가" }));
  await screen.findByRole("button", { name: "2. 부산시민공원" });
  const saved = JSON.parse(localStorage.getItem("busannow.course")).plan.stops;
  expect([saved[0], saved[2]]).toEqual(stops);
  expect(saved[1]).toMatchObject({
    place_id: "busan-citizens-park", start: `2026-11-21T${start}:00.000+09:00`, end: `2026-11-21T${confirmedEnd}:00.000+09:00`,
  });
  if (live) {
    expect(putCalls()).toEqual([[expect.stringContaining("/plan/add-park"), expect.objectContaining({ method: "PUT" })]]);
  }
});

it("renders multiple cafe recommendations in a single scrollable card group", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Recommend a cafe" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const rail = await screen.findByRole("group", { name: "Suggested places" });
  expect(rail).toHaveAttribute("data-multiple", "true");
  expect(within(rail).getAllByRole("article")).toHaveLength(2);
  expect(within(rail).queryByRole("button", { name: /Confirm/ })).not.toBeInTheDocument();
});

it("moves the trip highlight from the second stop to Busan Museum at 13:00", () => {
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
  vi.setSystemTime(new Date("2026-11-21T12:59:59+09:00"));
  const stops = [
    ["beach", "10:00", "11:00"],
    ["park", "12:00", "13:00"],
    ["museum", "13:00", "14:00"],
  ].map(([id, start, end]) => ({
    stop_id: id,
    place_id: id,
    start: `2026-11-21T${start}:00+09:00`,
    end: `2026-11-21T${end}:00+09:00`,
    locked: false,
  }));
  const places = ["Haeundae Beach", "Peace Park", "Busan Museum"].map((name, index) => ({
    place_id: stops[index].place_id, names: { en: name }, lat: 35.13 + index * 0.01, lng: 129.09,
  }));
  localStorage.setItem("busannow.language", "en");
  localStorage.setItem("busannow.course", JSON.stringify({
    plan: { plan_id: "timed-trip", date: "2026-11-21", profile: { language: "en" }, stops },
    places,
  }));
  const { unmount } = render(<App />);
  const click = (name) => fireEvent.click(screen.getByRole("button", { name, exact: true }));
  try {
    click("Itinerary");
    click("Start trip");
    expect(screen.getByRole("button", { name: "2. Peace Park", current: true })).toBeInTheDocument();
    click("Itinerary");
    const itinerary = within(screen.getByRole("region", { name: "Itinerary" }));
    expect(itinerary.getByRole("button", { name: /Peace Park/, current: true })).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1_000));

    expect(screen.getByRole("button", { name: "3. Busan Museum", current: true })).toBeInTheDocument();
    expect(itinerary.getByRole("button", { name: /Busan Museum/, current: true })).toBeInTheDocument();
    fireEvent.click(itinerary.getByRole("button", { name: /^1.*Haeundae Beach/, pressed: false }));
    expect(itinerary.getByRole("button", { name: /Busan Museum/, current: true })).toBeInTheDocument();
    click("Home");
    expect(screen.getByText("Busan Museum", { selector: ".trip-next strong" })).toBeVisible();
    expect(screen.getByText("Current stop", { selector: ".trip-next span" })).toBeVisible();
    act(() => {
      vi.setSystemTime(new Date("2026-11-21T11:30:00+09:00"));
      fireEvent.focus(window);
    });
    expect(screen.queryByText("Current stop", { selector: ".trip-next span" })).not.toBeInTheDocument();
  } finally {
    unmount();
    vi.useRealTimers();
  }
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
  expect(screen.getByText("AI leaves locked stops unchanged.")).toBeVisible();
  const lockedRow = within(screen.getAllByRole("listitem")[2]);
  await user.click(lockedRow.getByRole("button", { name: /^Lock stop/ }));
  expect(lockedRow.getByRole("button", { name: /^Unlock stop/, pressed: true })).toHaveTextContent("Fixed");
  expect(lockedRow.getByRole("button", { name: /^3/, pressed: false })).toBeInTheDocument();
  expect(lockedRow.queryByRole("button", { name: /Edit with AI|Edit visit time/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  const course = JSON.parse(localStorage.getItem("busannow.course")).plan;
  expect(course.stops[2].locked).toBe(true);
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
  vi.stubGlobal("fetch", vi.fn(async (url) => {
    if (url.endsWith("/plan/check")) return Response.json({ plan_id: plan.plan_id, issues: [], repairs: {}, places });
    if (url.endsWith("/chat")) return Response.json({ plan_id: plan.plan_id, session_id: "test-session", language: "en", answer: "No escape room found.", plan_changes: [] });
    return Response.json({ plan, places });
  }));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "일정", exact: true }));
  await user.click(screen.getAllByRole("button", { name: /AI로 수정/ })[0]);
  await user.type(screen.getByRole("textbox"), "공포 방탈출로 바꿔줘");
  await user.click(screen.getByRole("button", { name: "전송" }));
  expect(await screen.findByText("요청한 변경을 반영하지 못했어요. 기존 일정은 그대로예요.")).toHaveAttribute("lang", "ko");
});
