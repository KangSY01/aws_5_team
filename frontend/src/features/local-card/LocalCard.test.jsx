import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LocalCard from "./LocalCard.jsx";
import LocalCardPicker from "./LocalCardPicker.jsx";
import { COPY, LANGUAGES, PHRASES } from "./phrases.js";
import { SpeakError, clearSpeechCache, fetchSpeech } from "./speakClient.js";

class FakeAudio {
  static instances = [];
  constructor(src) {
    this.src = src;
    this.paused = true;
    FakeAudio.instances.push(this);
  }
  play() {
    this.paused = false;
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
}

beforeEach(() => {
  FakeAudio.instances = [];
  vi.stubGlobal("Audio", FakeAudio);
  clearSpeechCache();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body, status = 200) {
  return { status, json: () => Promise.resolve(body) };
}

describe("phrases", () => {
  it("has every phrase in Korean and all four user languages", () => {
    for (const phrase of PHRASES) {
      expect(phrase.ko.length).toBeGreaterThan(0);
      expect(phrase.ko.length).toBeLessThanOrEqual(500); // /speak 계약 상한
      for (const lang of LANGUAGES) expect(phrase[lang], `${phrase.id}.${lang}`).toBeTruthy();
    }
    expect(PHRASES.find((p) => p.id === "less_spicy").ko).toBe("덜 맵게 해 주실 수 있나요?"); // 장면 4 대본
    for (const lang of LANGUAGES) expect(Object.keys(COPY[lang])).toEqual(Object.keys(COPY.en));
  });
});

describe("fetchSpeech", () => {
  it("posts Korean text to /speak and returns a cached data URL", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ content_type: "audio/mpeg", audio_base64: "SUQz" }));
    const url = await fetchSpeech("  덜 맵게 해 주실 수 있나요? ", "ko", { baseUrl: "https://api.example/", fetchImpl });

    expect(url).toBe("data:audio/mpeg;base64,SUQz");
    const [target, init] = fetchImpl.mock.calls[0];
    expect(target).toBe("https://api.example/speak");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "덜 맵게 해 주실 수 있나요?", language: "ko" });

    await fetchSpeech("덜 맵게 해 주실 수 있나요?", "ko", { baseUrl: "https://api.example", fetchImpl });
    expect(fetchImpl).toHaveBeenCalledTimes(1); // 같은 문장은 다시 받지 않는다
  });

  it.each([
    ["empty text", "", null, "invalid_text"],
    ["too long", "가".repeat(501), null, "invalid_text"],
    ["http error", "안녕하세요", jsonResponse({ error: { code: "internal_error", message: "x" } }, 500), "http"],
    ["missing audio", "안녕하세요", jsonResponse({ content_type: "audio/mpeg" }), "invalid_response"],
  ])("fails on %s", async (_name, text, response, kind) => {
    const fetchImpl = vi.fn().mockResolvedValue(response);
    await expect(fetchSpeech(text, "ko", { baseUrl: "https://api.example", fetchImpl })).rejects.toMatchObject({ kind });
  });

  it("reports network failures", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(fetchSpeech("안녕하세요", "ko", { baseUrl: "https://api.example", fetchImpl })).rejects.toBeInstanceOf(SpeakError);
  });
});

describe("LocalCard", () => {
  it("shows the Korean text large with the meaning and plays Korean audio", async () => {
    const user = userEvent.setup();
    const speak = vi.fn().mockResolvedValue("data:audio/mpeg;base64,SUQz");
    const onClose = vi.fn();
    render(<LocalCard textKo="덜 맵게 해 주실 수 있나요?" translation="辛さを控えめにしてもらえますか？" language="ja" onClose={onClose} speak={speak} />);

    const dialog = screen.getByRole("dialog", { name: "現地の人に見せる" });
    expect(within(dialog).getByText("덜 맵게 해 주실 수 있나요?")).toHaveAttribute("lang", "ko");
    expect(within(dialog).getByText(/辛さを控えめに/)).toBeVisible();
    expect(screen.getByRole("button", { name: "閉じる" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: /韓国語で再生/ }));
    expect(speak).toHaveBeenCalledWith("덜 맵게 해 주실 수 있나요?", "ko");
    expect(FakeAudio.instances[0].src).toBe("data:audio/mpeg;base64,SUQz");
    expect(await screen.findByRole("button", { name: /再生中/ })).toBeVisible();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps the text on screen and explains when audio fails", async () => {
    const user = userEvent.setup();
    const speak = vi.fn().mockRejectedValue(new SpeakError("network"));
    render(<LocalCard textKo="화장실이 어디에 있나요?" language="en" onClose={() => {}} speak={speak} />);

    await user.click(screen.getByRole("button", { name: /Play in Korean/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't play the audio");
    expect(screen.getByText("화장실이 어디에 있나요?")).toBeVisible();
  });
});

describe("LocalCardPicker", () => {
  it("lists phrases in the user language and opens the Korean card", async () => {
    const user = userEvent.setup();
    render(<LocalCardPicker language="zh-Hant" speak={vi.fn()} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(PHRASES.length);
    await user.click(screen.getByRole("button", { name: /可以做得不那麼辣嗎/ }));
    const dialog = screen.getByRole("dialog", { name: "給當地人看" });
    expect(within(dialog).getByText("덜 맵게 해 주실 수 있나요?")).toBeVisible();

    await user.click(within(dialog).getByRole("button", { name: "關閉" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
