import { EventStreamCodec } from "@smithy/eventstream-codec";
import { fromUtf8, toUtf8 } from "@smithy/util-utf8";
import { requestJson } from "./planClient.js";

const codec = new EventStreamCodec(toUtf8, fromUtf8);
const string = (value) => ({ type: "string", value });

function audioEvent(body) {
  return codec.encode({
    headers: {
      ":message-type": string("event"),
      ":event-type": string("AudioEvent"),
      ":content-type": string("application/octet-stream"),
    },
    body,
  });
}

export function createPcmEncoder(inputRate, outputRate) {
  if (inputRate < outputRate) throw new Error("Unsupported microphone sample rate");
  let phase = 0;
  let sum = 0;
  let count = 0;
  return (samples) => {
    const bytes = new Uint8Array(Math.ceil(samples.length * outputRate / inputRate) * 2);
    const pcm = new DataView(bytes.buffer);
    let offset = 0;

    for (const sample of samples) {
      phase += outputRate;
      sum += sample;
      count += 1;
      if (phase < inputRate) continue;
      const value = Math.max(-1, Math.min(1, sum / count));
      pcm.setInt16(offset, Math.round(value * (value < 0 ? 32768 : 32767)), true);
      offset += 2;
      phase -= inputRate;
      sum = 0;
      count = 0;
    }
    return bytes.subarray(0, offset);
  };
}

export function recordChatVoice({ language, onListening, onResult, onDone, onError }) {
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio || !navigator.mediaDevices?.getUserMedia || !window.WebSocket) {
    onError("micUnsupported");
    return null;
  }

  const controller = new AbortController();
  const finalResults = new Map();
  let context, stream, source, processor, ws, timer;
  let stopping = false;

  function releaseMicrophone() {
    if (processor) {
      processor.onaudioprocess = null;
      processor.disconnect();
      processor = null;
    }
    source?.disconnect();
    source = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    if (context && context.state !== "closed") void context.close().catch(() => {});
    context = null;
  }

  function close() {
    if (controller.signal.aborted) return false;
    controller.abort();
    clearTimeout(timer);
    releaseMicrophone();
    if (ws && ws.readyState < WebSocket.CLOSING) ws.close();
    return true;
  }

  function finish() {
    if (close()) onDone(finalResults.size > 0);
  }

  function fail(error) {
    if (!close()) return;
    onError(["NotAllowedError", "SecurityError", "NotFoundError"].includes(error?.name) ? "micDenied" : "micError");
  }

  async function connect() {
    context = new Audio();
    // Start resuming during the microphone button's user gesture.
    const resume = context.resume().then(() => true, () => false);
    const microphone = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
    if (controller.signal.aborted) {
      microphone.getTracks().forEach((track) => track.stop());
      return;
    }
    stream = microphone;
    const { url, sample_rate: rate, media_encoding: encoding } = await requestJson("/voice/url", {
      signal: controller.signal,
      request: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language }) },
    });
    if (controller.signal.aborted) return;
    if (new URL(url).protocol !== "wss:" || encoding !== "pcm" || !Number.isInteger(rate) || rate <= 0) {
      throw new Error("Invalid voice stream settings");
    }
    if (!await resume) throw new Error("Unable to start microphone audio");
    if (controller.signal.aborted) return;

    const encodePcm = createPcmEncoder(context.sampleRate, rate);
    ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    timer = setTimeout(() => fail(), 12000);
    ws.onopen = () => {
      if (controller.signal.aborted) return;
      clearTimeout(timer);
      try {
        source = context.createMediaStreamSource(stream);
        processor = context.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = ({ inputBuffer }) => {
          if (stopping || ws.readyState !== WebSocket.OPEN) return;
          const pcm = encodePcm(inputBuffer.getChannelData(0));
          if (pcm.length) ws.send(audioEvent(pcm));
        };
        source.connect(processor);
        // The processor emits silent output while its input is captured.
        processor.connect(context.destination);
        onListening();
      } catch (error) {
        fail(error);
      }
    };
    ws.onmessage = ({ data }) => {
      if (controller.signal.aborted) return;
      try {
        const frame = codec.decode(new Uint8Array(data));
        if (frame.headers[":message-type"]?.value !== "event") {
          fail();
          return;
        }
        if (frame.headers[":event-type"]?.value !== "TranscriptEvent") return;
        const { Transcript } = JSON.parse(toUtf8(frame.body));
        let partial = "";
        for (const result of Transcript?.Results ?? []) {
          const text = result.Alternatives?.[0]?.Transcript?.trim();
          if (!text) continue;
          if (result.IsPartial) partial = text;
          else finalResults.set(result.ResultId ?? result.StartTime ?? finalResults.size, text);
        }
        const separator = language === "ja" || language.startsWith("zh") ? "" : " ";
        onResult([...finalResults.values()].join(separator), partial);
      } catch (error) {
        fail(error);
      }
    };
    ws.onerror = fail;
    ws.onclose = () => { if (stopping) finish(); else fail(); };
  }

  void connect().catch(fail);
  return {
    cancel: close,
    stop() {
      if (controller.signal.aborted || stopping) return;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        finish();
        return;
      }
      stopping = true;
      releaseMicrophone();
      try {
        ws.send(audioEvent(new Uint8Array()));
        timer = setTimeout(finish, 5000);
      } catch (error) {
        fail(error);
      }
    },
  };
}
