import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { resolvePlaceName } from "../lib/resolvePlaceName.js";
import { recommendDemo } from "../lib/demoPlanner.js";

beforeEach(() => {
  vi.stubEnv("VITE_API_BASE_URL", "");
  localStorage.setItem("busannow.traveler-profile", "{}");
});

afterEach(() => {
  vi.unstubAllEnvs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("opens general AI chat without an itinerary and continues the same conversation", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(Response.json({ session_id: "general", plan_id: "chat-plan", language: "en",
      answer: "Try Gwangalli Beach.", sources: [{ tool: "get_weather", id: "forecast", title: "Busan forecast" }] }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ session_id: "general", plan_id: "chat-plan", language: "en", answer: "An evening walk is an option." })))
    .mockResolvedValueOnce(Response.json({ error: { code: "internal_error", message: "Server error" } }, { status: 500 }));
  vi.stubGlobal("fetch", (url, request) => String(url).includes("/events?")
    ? Promise.resolve(Response.json({ date: String(url).split("=").at(-1), events: [] }))
    : fetchMock(url, request));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));

  function send(message) {
    fireEvent.change(screen.getByRole("textbox"), { target: { value: message } });
    const button = screen.getByRole("button", { name: "Send" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
  }

  send("Where can I see the sea?");
  const loading = within(screen.getByRole("log")).getByRole("status");
  expect(loading).toHaveClass("chat-course-status");
  expect(loading).toHaveTextContent("Finding your route…");
  expect(await screen.findByText("Try Gwangalli Beach.")).toBeVisible();
  expect(screen.getByText(/Korea Meteorological Administration/)).toBeVisible();
  expect(screen.queryByText("Finding your route…")).not.toBeInTheDocument();
  send("What about the evening?");
  expect(await screen.findByText("An evening walk is an option.")).toBeVisible();
  expect(fetchMock.mock.calls.map(([, request]) => JSON.parse(request.body))).toEqual([
    expect.objectContaining({ message: "Where can I see the sea?", session_id: null, plan_id: null }),
    expect.objectContaining({ message: "What about the evening?", session_id: "general", plan_id: "chat-plan" }),
  ]);
  send("Find another route.");
  expect(within(screen.getByRole("log")).getByRole("status")).toHaveTextContent("Finding your route…");
  expect(await screen.findByRole("alert")).toHaveTextContent("POST /chat · HTTP 500");
  expect(screen.queryByText("Finding your route…")).not.toBeInTheDocument();
  expect(localStorage.getItem("busannow.course")).toBeNull();
});

it("opens a walking path from a structured return option in chat", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const pathRequest = vi.fn();
  vi.stubGlobal("fetch", async (url, request) => {
    if (url.endsWith("/chat")) return Response.json({
      session_id: "return-session", plan_id: "return-plan", language: "en", answer: "Try Dongbaek station.",
      return_routes: {
        origin_place_id: "haeundae-beach",
        destination: { names: { en: "Seomyeon" } },
        options: [{ station: { names: { en: "Dongbaek" }, lat: 35.161484, lng: 129.147897 },
          travel_min: 51, depart_at: "2026-11-28T22:00:00+09:00", time_source: "kakao" }],
      },
    });
    if (url.endsWith("/routes/pedestrian")) {
      pathRequest(JSON.parse(request.body));
      return Response.json({ paths: [[[129.16, 35.16], [129.147897, 35.161484]]] });
    }
    return Response.json({ events: [] });
  });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "How do I get back after the festival?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const walk = await screen.findByRole("button", { name: "Show walking route" });
  expect(screen.getByText("Dongbaek → Seomyeon")).toBeVisible();
  fireEvent.click(walk);
  await waitFor(() => expect(document.querySelector(".travel-preview")).toHaveAttribute("data-sheet", "closed"));
  expect(pathRequest).toHaveBeenCalledWith(expect.objectContaining({
    destination: { lat: 35.161484, lng: 129.147897 },
  }));
  expect(document.querySelector(".leaflet-control-attribution")).toHaveTextContent("© TMAP");
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
  expect(card.getByText("추천 이유")).toBeVisible();
  expect(card.getByText("채팅에서 요청하신 장소예요.")).toBeVisible();
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
  expect(within(rail).getAllByText("This café matches your request.")).toHaveLength(2);
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
  const cinema = { place_id: "busan-cinema-street", names: { en: "Busan Cine Road", ja: "釜山映画の通り" } };
  const alternatives = new Map([[cinema.place_id, cinema]]);
  expect(resolvePlaceName(cinema, alternatives, "ko").name).toBe("부산 영화의 거리");
  expect(resolvePlaceName(cinema, alternatives, "en").name).toBe("Busan Cine Road");
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

it("confirms itinerary reset, preserves preferences, and permits a new course without old AI suggestions", async () => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; };
  }
  const preferences = { regions: ["oldtown"], duration: "half", activities: ["mural_village"] };
  const course = await recommendDemo(preferences, "en");
  course.plan.stops = course.plan.stops.slice(0, 2).map((stop, index) => ({
    ...stop,
    start: "2026-11-28T" + (index ? "14" : "10") + ":00:00+09:00",
    end: "2026-11-28T" + (index ? "15" : "11") + ":00:00+09:00",
  }));
  const savedCourse = { ...course, preferences };
  localStorage.setItem("busannow.course", JSON.stringify(savedCourse));
  localStorage.setItem("busannow.preferences", JSON.stringify(preferences));
  localStorage.setItem("busannow.language", "en");
  localStorage.setItem("busannow.activeTrip", course.plan.plan_id);
  render(<App />);
  const click = (name) => fireEvent.click(screen.getByRole("button", { name, exact: true }));
  click("Itinerary");
  expect(screen.queryByLabelText("Itinerary options")).not.toBeInTheDocument();
  click("End trip");
  click("Itinerary");

  fireEvent.click(screen.getByRole("button", { name: "Edit with AI · Jagalchi Market" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Try a different market" } });
  click("Send");
  await screen.findByRole("button", { name: "Apply to itinerary" });

  click("Itinerary");
  const openReset = () => {
    fireEvent.click(screen.getByLabelText("Itinerary options"));
    click("Reset itinerary");
    return screen.getByRole("dialog", { name: "Clear your current itinerary?" });
  };
  fireEvent.click(within(openReset()).getByRole("button", { name: "Cancel", exact: true }));
  expect(JSON.parse(localStorage.getItem("busannow.course"))).toEqual(savedCourse);
  expect(document.querySelectorAll(".busan-map-pin")).toHaveLength(course.plan.stops.length);

  fireEvent.click(within(openReset()).getByRole("button", { name: "Clear itinerary", exact: true }));
  expect(screen.getByText("There are no stops in this itinerary.")).toBeVisible();
  expect(screen.queryByLabelText("Itinerary options")).not.toBeInTheDocument();
  expect(document.querySelector(".busan-map-pin, .busan-visit-line")).toBeNull();
  expect(localStorage.getItem("busannow.course")).toBeNull();
  expect(localStorage.getItem("busannow.activeTrip")).toBeNull();
  expect(JSON.parse(localStorage.getItem("busannow.preferences"))).toEqual(preferences);
  expect(localStorage.getItem("busannow.language")).toBe("en");

  click("Get an AI itinerary");
  expect(screen.getByRole("button", { name: "Remove area · Nampo · Yeongdo" })).toBeVisible();
  click("Create itinerary");
  await screen.findAllByRole("button", { name: /^Edit with AI/ });
  click("Chat");
  expect(screen.queryByRole("button", { name: "Apply to itinerary" })).not.toBeInTheDocument();
  expect(document.querySelectorAll(".busan-map-pin").length).toBeGreaterThan(0);
});

it("shows API events on the map and falls back to their Korean names", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  localStorage.setItem("busannow.language", "ja");
  const fetchEvents = vi.fn(async (url) => {
    const date = new URL(url, "https://api.example.test").searchParams.get("date");
    return Response.json({ date, events: [{
      contentid: "2048902", name: "해운대 빛축제", names: { ko: "해운대 빛축제", en: "Haeundae Light Festival" },
      type: "festival", lat: 35.1592056511, lng: 129.1615365475,
      main_place_id: null, place_ids: [],
      start: date + "T18:00:00+09:00", end: date + "T23:00:00+09:00",
      period_start: "2026-11-28T18:00:00+09:00", period_end: "2027-01-10T23:00:00+09:00",
    }] });
  });
  vi.stubGlobal("fetch", (url) => String(url).includes("/events?") ? fetchEvents(url) : Promise.reject(new Error()));
  render(<App />);
  const marker = await screen.findByLabelText("해운대 빛축제");
  expect(marker).toHaveClass("busan-event-festival");
  expect(fetchEvents).toHaveBeenCalledWith(expect.stringMatching(/\/events\?date=\d{4}-\d{2}-\d{2}$/));
  fireEvent.click(marker);
  expect(screen.getByRole("heading", { name: "해운대 빛축제" })).toBeVisible();
  expect(screen.getByText("18:00 – 23:00")).toBeVisible();
});

it("turns grounded chat recommendations into cards and keeps weather guidance in the reply", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubGlobal("fetch", async (url) => {
    if (!String(url).endsWith("/chat")) return Response.json({});
    return Response.json({
      session_id: "recommendations", plan_id: "chat-plan", language: "en",
      answer: "Try these places. - **Haeundae Beach**: Walk along the sand. - **Jagalchi Market**: Browse seafood stalls. The forecast starts at 6 p.m.",
      sources: [
        { tool: "search_places", id: "haeundae-beach", title: "Haeundae Beach" },
        { tool: "get_place_info", id: "jagalchi-market", title: "Jagalchi Market" },
        { tool: "get_weather", id: "busan", title: "Weather" },
      ],
    });
  });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Suggest afternoon activities in Busan" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const rail = await screen.findByRole("group", { name: "Suggested places" });
  expect(rail).toHaveAttribute("data-multiple", "true");
  expect(within(rail).getAllByRole("article")).toHaveLength(2);
  expect(within(rail).getByRole("heading", { name: "Haeundae Beach" })).toBeVisible();
  expect(within(rail).getByText("Browse seafood stalls.")).toBeVisible();
  expect(screen.getByText(/The forecast starts at 6 p.m./)).toHaveClass("chat-bubble");
});

it("shows live activity details without itinerary controls even when a course exists", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const course = await recommendDemo({ regions: ["oldtown"], duration: "half", activities: [] }, "en");
  localStorage.setItem("busannow.course", JSON.stringify(course));
  const activityCalls = [];
  vi.stubGlobal("fetch", async (url) => {
    const parsed = new URL(url, "https://api.example.test");
    if (!parsed.pathname.endsWith("/activities")) return Response.json({});
    activityCalls.push(parsed.searchParams);
    return Response.json({ places: [{ id: "123", name: "Test Escape Room", address: "Test street",
      phone: "051-000-0000", category: "Entertainment > Escape Room", url: "https://place.map.kakao.com/123" }] });
  });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Chat", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "해운대에 있는 방탈출 찾아줘" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const card = within(await screen.findByRole("article"));
  expect(card.getByRole("heading", { name: "Test Escape Room" })).toBeVisible();
  expect(card.getByText("Test street")).toBeVisible();
  expect(card.getByRole("link", { name: "Place details" })).toHaveAttribute("href", "https://place.map.kakao.com/123");
  expect(card.queryByLabelText("Start time")).not.toBeInTheDocument();
  expect(card.queryByRole("button", { name: /add to itinerary/i })).not.toBeInTheDocument();
  expect(activityCalls.map((params) => Object.fromEntries(params))).toEqual([{ area: "해운대", kind: "escape_room" }]);
});

it("opens only the translation menu on the map from other travel tabs", () => {
  render(<App />);
  const click = (name) => fireEvent.click(screen.getByRole("button", { name, exact: true }));
  for (const name of ["Chat", "Itinerary", "Profile"]) {
    click(name);
    click("Translate");
    const app = document.querySelector(".travel-preview");
    expect(app).toHaveAttribute("data-page", "map");
    expect(app).toHaveAttribute("data-sheet", "closed");
    expect(screen.getByRole("group", { name: "Translate" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Translate", exact: true })).toHaveAttribute("aria-current", "page");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Translate" })).not.toBeInTheDocument();
  }
});

it("keeps a saved traveler profile across reloads and sends only its notes with itinerary requests", async () => {
  localStorage.removeItem("busannow.traveler-profile");
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  const chat = vi.fn(() => Response.json({}, { status: 500 }));
  vi.stubGlobal("fetch", async (url, request) => String(url).endsWith("/chat")
    ? chat(JSON.parse(request.body)) : Response.json({ events: [] }));
  const first = render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Name or nickname"), "Private nickname");
  await user.type(screen.getByLabelText("Age"), "28");
  await user.selectOptions(screen.getByLabelText("Gender"), "woman");
  await user.type(screen.getByLabelText("Nationality"), "Japan");
  await user.type(screen.getByLabelText("Travel notes"), "Please keep walking distances short.");
  await user.click(screen.getByRole("button", { name: "Save and start" }));
  expect(screen.getByRole("button", { name: "Home", exact: true })).toBeInTheDocument();
  first.unmount();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Profile", exact: true }));
  expect(screen.getByText("Private nickname")).toBeVisible();
  expect(screen.getByText("28 years · Woman · Japan")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Itinerary", exact: true }));
  await user.click(screen.getByRole("button", { name: "Get an AI itinerary" }));
  await user.click(screen.getByRole("button", { name: "Create itinerary" }));
  await waitFor(() => expect(chat).toHaveBeenCalledTimes(1));
  const request = chat.mock.calls[0][0];
  expect(request.message).toContain("Please keep walking distances short.");
  expect(JSON.stringify(request)).not.toMatch(/Private nickname|Japan|woman|\b28\b/);
});

it("remembers skipping traveler setup and lets the traveler edit their optional profile later", async () => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; };
  }
  localStorage.removeItem("busannow.traveler-profile");
  const first = render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Name or nickname"), "Discarded nickname");
  await user.click(screen.getByRole("button", { name: "Later", exact: true }));
  first.unmount();
  render(<App />);
  expect(screen.queryByRole("heading", { name: "Traveler profile" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Profile", exact: true }));
  await user.click(screen.getByRole("button", { name: "Edit profile", exact: true }));
  expect(screen.getByLabelText("Name or nickname")).toHaveValue("");
  await user.type(screen.getByLabelText("Name or nickname"), "New nickname");
  await user.click(screen.getByRole("button", { name: "Save", exact: true }));
  expect(screen.getByText("New nickname")).toBeVisible();
  expect(screen.queryByText("Prefer not to answer")).not.toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("busannow.traveler-profile")).name).toBe("New nickname");
});
