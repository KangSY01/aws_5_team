import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { reloadDemoState, setDemo } from "../demo-panel/demoStore.js";
import ChatSources from "./ChatSources.jsx";
import RainNotice from "./RainNotice.jsx";
import { PROVIDERS, RAIN_COPY, SOURCES_LABEL, providerNames } from "./copy.js";

const LANGUAGES = ["ko", "en", "ja", "zh-Hans", "zh-Hant"];

beforeEach(() => {
  localStorage.clear();
  reloadDemoState();
});

describe("providerNames", () => {
  it("maps tools to providers in first-seen order without duplicates", () => {
    const sources = [
      { tool: "get_weather", id: "2026-11-28", title: "weather" },
      { tool: "get_crowd", id: "haeundae-beach", title: "crowd" },
      { tool: "search_places", id: "haeundae-beach", title: "Haeundae" },
      { tool: "get_return_options", id: "2026-11-28:Haeundae>Seomyeon", title: "return" },
    ];
    expect(providerNames(sources, "ko")).toEqual(["기상청", "한국관광공사", "카카오맵", "부산교통공사"]);
  });

  it("skips plan tools, computed estimates and unknown tools", () => {
    const sources = [{ tool: "create_plan" }, { tool: "get_travel_time" }, { tool: "unknown" }, null];
    expect(providerNames(sources, "en")).toEqual([]);
    expect(providerNames(undefined, "en")).toEqual([]);
  });

  it("has every provider and label in every language", () => {
    for (const language of LANGUAGES) {
      expect(SOURCES_LABEL[language]).toBeTruthy();
      expect(RAIN_COPY[language].title).toBeTruthy();
      for (const provider of Object.values(PROVIDERS)) expect(provider[language]).toBeTruthy();
    }
  });
});

describe("ChatSources", () => {
  it("shows the label and providers under an answer", () => {
    render(<ChatSources sources={[{ tool: "get_events", id: "e1", title: "festival" }]} language="ja" />);
    expect(screen.getByText("出典")).toBeInTheDocument();
    expect(screen.getByText(/韓国観光公社/)).toBeInTheDocument();
  });

  it("renders nothing when there is no source to show", () => {
    const { container } = render(<ChatSources sources={[]} language="ko" />);
    expect(container).toBeEmptyDOMElement();
    const { container: planOnly } = render(<ChatSources sources={[{ tool: "create_plan", id: "p", title: "p" }]} language="ko" />);
    expect(planOnly).toBeEmptyDOMElement();
  });
});

describe("RainNotice", () => {
  it("stays hidden while the demo switch is off", () => {
    act(() => setDemo({ enabled: false, weatherPreset: "rain-afternoon" }));
    const { container } = render(<RainNotice language="ko" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows only for the rain-afternoon preset and hides when the demo changes", () => {
    act(() => setDemo({ enabled: true, weatherPreset: "rain-afternoon" }));
    render(<RainNotice language="ja" />);
    expect(screen.getByRole("status", { name: "雨の予報があります" })).toHaveTextContent("13:00–15:00");

    act(() => setDemo({ weatherPreset: null }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    act(() => setDemo({ weatherPreset: "rain-afternoon" }));
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => setDemo({ enabled: false }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("mentions the place, opens options and can be dismissed", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    act(() => setDemo({ enabled: true, weatherPreset: "rain-afternoon" }));
    render(<RainNotice language="ko" placeName="해운대해수욕장" onOpen={onOpen} />);
    expect(screen.getByRole("status")).toHaveTextContent("해운대해수욕장 방문 시간(13:00–15:00)");

    await user.click(screen.getByRole("button", { name: "대안 보기" }));
    expect(onOpen).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("has no options button without onOpen", () => {
    act(() => setDemo({ enabled: true, weatherPreset: "rain-afternoon" }));
    render(<RainNotice language="en" />);
    expect(screen.queryByRole("button", { name: "See options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
