import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import DemoPanel from "./DemoPanel.jsx";
import {
  STORAGE_KEY,
  applyScene,
  fromLocalInput,
  getDemoOverride,
  getDemoState,
  reloadDemoState,
  resetDemo,
  setDemo,
  toLocalInput,
  withDemo,
} from "./demoStore.js";

beforeEach(() => {
  localStorage.clear();
  reloadDemoState();
});

describe("demoStore", () => {
  it("adds nothing while the switch is off", () => {
    setDemo({ now: "2026-11-28T13:00:00+09:00", weatherPreset: "rain-afternoon" });
    expect(getDemoOverride()).toBeNull();
    expect(withDemo({ plan_id: "plan-1" })).toEqual({ plan_id: "plan-1" });
  });

  it("builds the contract demo object only from chosen values", () => {
    setDemo({ enabled: true });
    expect(getDemoOverride()).toBeNull(); // 켜기만 하고 고른 값이 없으면 평소대로
    setDemo({ now: "2026-11-28T09:00:00+09:00" });
    expect(withDemo({ plan_id: "plan-1" })).toEqual({ plan_id: "plan-1", demo: { now: "2026-11-28T09:00:00+09:00" } });
    setDemo({ weatherPreset: "rain-afternoon" });
    expect(getDemoOverride()).toEqual({ now: "2026-11-28T09:00:00+09:00", weather_preset: "rain-afternoon" });
  });

  it("applies a scene and persists it across reloads", () => {
    applyScene("scene5");
    expect(getDemoOverride()).toEqual({ now: "2026-11-28T13:00:00+09:00", weather_preset: "rain-afternoon" });
    reloadDemoState();
    expect(getDemoState()).toEqual({ enabled: true, now: "2026-11-28T13:00:00+09:00", weatherPreset: "rain-afternoon" });
    resetDemo();
    expect(getDemoOverride()).toBeNull();
  });

  it("drops unknown presets and malformed times instead of sending them", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ enabled: true, now: "tomorrow", weatherPreset: "snow" }));
    reloadDemoState();
    expect(getDemoState()).toEqual({ enabled: true, now: null, weatherPreset: null });
    localStorage.setItem(STORAGE_KEY, "{broken");
    reloadDemoState();
    expect(getDemoState().enabled).toBe(false);
  });

  it("converts between datetime-local values and KST ISO times", () => {
    expect(fromLocalInput("2026-11-28T13:00")).toBe("2026-11-28T13:00:00+09:00");
    expect(fromLocalInput("")).toBeNull();
    expect(toLocalInput("2026-11-28T13:00:00+09:00")).toBe("2026-11-28T13:00");
    expect(toLocalInput("2026-11-28T04:00:00Z")).toBe("2026-11-28T13:00");
    expect(toLocalInput(null)).toBe("");
  });
});

describe("DemoPanel", () => {
  it("opens, applies a scene shortcut and shows the summary", async () => {
    const user = userEvent.setup();
    render(<DemoPanel />);
    const toggle = screen.getByRole("button", { name: /DEMO/ });
    expect(toggle).toHaveTextContent("꺼짐");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: "장면 5 오후 비" }));

    expect(screen.getByRole("checkbox", { name: "데모 스위치 켜기" })).toBeChecked();
    expect(screen.getByLabelText("기준 시각 (한국 시각)")).toHaveValue("2026-11-28T13:00");
    expect(screen.getByLabelText("날씨")).toHaveValue("rain-afternoon");
    expect(toggle).toHaveTextContent("11/28 13:00 · 11/28 13~15시 비");
  });

  it("edits time and weather and can switch off", async () => {
    const user = userEvent.setup();
    render(<DemoPanel defaultOpen />);
    await user.click(screen.getByRole("checkbox", { name: "데모 스위치 켜기" }));
    await user.selectOptions(screen.getByLabelText("날씨"), "rain-afternoon");
    expect(getDemoOverride()).toEqual({ now: "2026-11-28T09:00:00+09:00", weather_preset: "rain-afternoon" });

    await user.selectOptions(screen.getByLabelText("날씨"), "");
    expect(getDemoOverride()).toEqual({ now: "2026-11-28T09:00:00+09:00" });

    await user.click(screen.getByRole("button", { name: "장면 7 귀가" }));
    await user.click(screen.getByRole("checkbox", { name: "데모 스위치 켜기" }));
    expect(getDemoOverride()).toBeNull();

    await user.click(screen.getByRole("button", { name: "초기화" }));
    expect(getDemoState()).toEqual({ enabled: false, now: null, weatherPreset: null });
  });
});
