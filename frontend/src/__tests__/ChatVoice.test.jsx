import { EventStreamCodec } from "@smithy/eventstream-codec";
import { fromUtf8, toUtf8 } from "@smithy/util-utf8";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { createPcmEncoder } from "../api/chatVoice.js";

const codec = new EventStreamCodec(toUtf8, fromUtf8);

beforeEach(() => localStorage.setItem("busannow.traveler-profile", "{}"));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

it("resamples mono PCM across chunk boundaries in little-endian order", () => {
  const encode = createPcmEncoder(48000, 16000);
  expect([...encode([1, 1])]).toEqual([]);
  expect([...encode([1, -1, -1, -1])]).toEqual([255, 127, 0, 128]);
});

function setUpVoice() {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  localStorage.setItem("busannow.language", "ja");
  const stopTrack = vi.fn();
  const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
  vi.stubGlobal("navigator", Object.create(navigator, { mediaDevices: { value: { getUserMedia } } }));
  const processor = { connect: vi.fn(), disconnect: vi.fn() };
  class Audio {
    sampleRate = 48000;
    destination = {};
    resume = vi.fn().mockResolvedValue(undefined);
    close = vi.fn().mockResolvedValue(undefined);
    createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
    createScriptProcessor = vi.fn(() => processor);
  }
  vi.stubGlobal("AudioContext", Audio);
  let socket;
  class Socket {
    static OPEN = 1;
    static CLOSING = 2;
    readyState = 0;
    send = vi.fn();
    close = vi.fn();
    constructor() { socket = this; }
  }
  vi.stubGlobal("WebSocket", Socket);

  const fetchMock = vi.fn(async (url) => {
    if (url.endsWith("/voice/url")) return Response.json({
      url: "wss://example.test/transcribe", sample_rate: 16000, media_encoding: "pcm", expires_in: 300,
    });
    if (url.endsWith("/chat")) return Response.json({
      plan_id: "chat-plan", session_id: "chat-session", language: "ja", answer: "釜山へようこそ。",
    });
    return Response.json({});
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "チャット", exact: true }));
  return { fetchMock, getUserMedia, getSocket: () => socket, processor, stopTrack };
}

it("puts the final Japanese transcript in the chat draft and submits it only after confirmation", async () => {
  const { getUserMedia, getSocket, processor, stopTrack, fetchMock } = setUpVoice();
  fireEvent.click(screen.getByRole("button", { name: "音声入力" }));
  await waitFor(() => expect(getSocket()).toBeDefined());
  expect(getUserMedia).toHaveBeenCalledWith({ audio: { channelCount: 1, echoCancellation: true } });
  expect(JSON.parse(fetchMock.mock.calls.find(([url]) => url.endsWith("/voice/url"))[1].body)).toEqual({ language: "ja" });
  const socket = getSocket();
  socket.readyState = 1;
  act(() => socket.onopen());
  processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array([1, 1, 1]) } });
  const frame = codec.decode(socket.send.mock.calls[0][0]);
  expect(frame.headers[":event-type"].value).toBe("AudioEvent");
  expect([...frame.body]).toEqual([255, 127]);
  const receive = (text, isPartial) => {
    const headers = Object.fromEntries([["message-type", "event"], ["event-type", "TranscriptEvent"]]
      .map(([key, value]) => [":" + key, { type: "string", value }]));
    socket.onmessage({ data: codec.encode({
      headers,
      body: fromUtf8(JSON.stringify({ Transcript: { Results: [{
        IsPartial: isPartial, ResultId: "voice-1", Alternatives: [{ Transcript: text }],
      }] } })),
    }).buffer });
  };
  act(() => receive("釜山", true));
  expect(await screen.findByText("釜山", { exact: true })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "停止" }));
  expect(stopTrack).toHaveBeenCalledOnce();
  expect(codec.decode(socket.send.mock.calls.at(-1)[0]).body).toHaveLength(0);
  act(() => {
    receive("釜山を案内してください。", false);
    socket.readyState = 3;
    socket.onclose();
  });
  await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("釜山を案内してください。"));
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/chat"))).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "送信" }));
  expect(await screen.findByText("釜山へようこそ。")).toBeVisible();
  const [, request] = fetchMock.mock.calls.find(([url]) => url.endsWith("/chat"));
  expect(JSON.parse(request.body)).toMatchObject({
    message: "釜山を案内してください。", profile: { language: "ja" },
  });
});

it("lets the user type after microphone permission is denied", async () => {
  const { getUserMedia, fetchMock } = setUpVoice();
  getUserMedia.mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"));
  fireEvent.click(screen.getByRole("button", { name: "音声入力" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("マイクを使用できません");
  expect(screen.getByRole("textbox")).not.toHaveAttribute("readonly");
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/voice/url"))).toBe(false);
});
