# 음성 입력 연결 가이드 (A → C)

음성은 서버를 거치지 않는다. 백엔드는 Amazon Transcribe Streaming 에 연결할 **서명된 WebSocket 주소만** 발급하고,
브라우저가 마이크 소리를 Transcribe 로 직접 보내 인식된 문장을 받는다. 그 문장을 채팅 입력창에 넣거나 `POST /chat` 으로 보낸다.

```
마이크 ─ 브라우저 ──(1) POST /voice/url {language}──▶ Lambda (서명만, 오디오 없음)
           │◀──────── {url, expires_in, sample_rate, media_encoding}
           ├──(2) WebSocket 연결 (300초 안에) ──▶ Transcribe Streaming (ap-northeast-2)
           ├──(3) 16kHz 16비트 PCM 조각을 이벤트 스트림으로 보냄
           │◀──(4) TranscriptEvent (중간 결과 IsPartial=true, 확정 결과 false)
           └──(5) 확정 문장 → 입력창 표시 → POST /chat {message, profile.language}
```

백엔드 코드: `backend/app/voice/` (`languages.py` 언어 표, `presign.py` 서명, `service.py` API). 경로 연결은 `backend/app/handler.py`.

## 1. API: `POST /voice/url`

계약: `docs/api-contract.md` 「POST /voice/url」 (`VoiceUrlRequest`, `VoiceUrlResponse`). 형식은 바꾸지 않았다.

요청
```json
{ "language": "ja" }
```
- `language`: 사용자가 말하는 언어. 프로필 언어와 같은 값 `en` / `ja` / `zh-Hans` / `zh-Hant`. 그 밖의 값은 `422 validation_error`.

응답
```json
{
  "url": "wss://transcribestreaming.ap-northeast-2.amazonaws.com:8443/stream-transcription-websocket?language-code=ja-JP&media-encoding=pcm&sample-rate=16000&X-Amz-Algorithm=AWS4-HMAC-SHA256&...&X-Amz-Signature=...",
  "expires_in": 300,
  "sample_rate": 16000,
  "media_encoding": "pcm"
}
```
- `url`: **300초 안에** WebSocket 연결을 시작해야 한다. 녹음할 때마다 새로 받는다. 연결된 뒤에는 녹음이 300초를 넘어도 된다.
- `sample_rate`·`media_encoding`: 이 값으로 서명했으므로 오디오를 반드시 16000Hz, 16비트 PCM(리틀 엔디언), 모노로 보낸다.
- `url` 에는 임시 세션 토큰이 들어 있다. 화면·콘솔 로그에 출력하지 않는다. 서버도 로그에 쓰지 않는다.
- 오류: `400 bad_request`(JSON 아님), `422 validation_error`(언어), `500 internal_error`(서버 설정·자격 증명. 상세 사유는 CloudWatch 에만 있다).
- 로컬(`USE_MOCK=1`)은 연결되지 않는 `wss://mock-transcribe.invalid/...` 를 돌려준다. 실제 인식은 배포 API 로 확인한다.

## 2. 언어: 인식 언어 코드와 결과 문장 언어

| 앱 언어 (`language`) | Transcribe 인식 코드 | 결과 문장 | `/chat` 의 `profile.language` |
|---|---|---|---|
| `en` | `en-US` | 영어 | `en` |
| `ja` | `ja-JP` | 일본어 | `ja` |
| `zh-Hans` | `zh-CN` | 중국어 **간체** | `zh-Hans` |
| `zh-Hant` | `zh-TW` | 중국어 **번체** | `zh-Hant` |

- 인식 코드는 서버가 정해서 URL 에 넣는다. 프론트엔드는 앱 언어만 보낸다.
- 중국어는 간체·번체가 인식 코드로 갈린다. 번체 사용자가 `zh-Hans` 로 녹음하면 간체 문장이 나온다.
- 네 언어 모두 서울 리전 스트리밍을 지원한다 ([지원 언어](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html), [엔드포인트](https://docs.aws.amazon.com/general/latest/gr/transcribe.html)).

## 3. 브라우저 구현 (C)

필요 패키지: `@smithy/eventstream-codec`, `@smithy/util-utf8` (`package.json` 에 추가). Transcribe 는 오디오 조각을 AWS 이벤트 스트림
형식(헤더 + CRC)으로 감싸야 받기 때문에, 이 인코더가 필요하다 ([규격](https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html)).

```js
import { EventStreamCodec } from "@smithy/eventstream-codec";
import { fromUtf8, toUtf8 } from "@smithy/util-utf8";

const codec = new EventStreamCodec(toUtf8, fromUtf8);
const str = (value) => ({ type: "string", value });
const audioEvent = (bytes) => codec.encode({
  headers: { ":content-type": str("application/octet-stream"), ":event-type": str("AudioEvent"), ":message-type": str("event") },
  body: bytes,
});

// Float32(-1~1) → 16비트 PCM 리틀 엔디언
function toPcm16(float32) {
  const out = new DataView(new ArrayBuffer(float32.length * 2));
  float32.forEach((s, i) => out.setInt16(i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Uint8Array(out.buffer);
}

export async function startVoiceInput({ apiBase, language, onPartial, onFinal, onError }) {
  const res = await fetch(`${apiBase}/voice/url`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ language }),
  });
  if (!res.ok) throw new Error(`voice url ${res.status}`);
  const { url, sample_rate } = await res.json();

  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
  const ctx = new AudioContext({ sampleRate: sample_rate });          // 브라우저가 16kHz 로 바꿔 준다 (Chrome·Edge·Safari)
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(1024, 1, 1);            // 해커톤용. 정식으로는 AudioWorklet
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    processor.onaudioprocess = (e) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(audioEvent(toPcm16(e.inputBuffer.getChannelData(0))));
    };
    source.connect(processor);
    processor.connect(ctx.destination);
  };
  ws.onmessage = (e) => {
    const msg = codec.decode(new Uint8Array(e.data));
    const type = msg.headers[":message-type"]?.value;
    const body = JSON.parse(toUtf8(msg.body) || "{}");
    if (type === "exception") return onError?.(msg.headers[":exception-type"]?.value, body.Message);
    for (const r of body.Transcript?.Results ?? []) {
      const text = r.Alternatives?.[0]?.Transcript ?? "";
      if (r.IsPartial) onPartial?.(text); else onFinal?.(text);   // 확정 문장만 이어 붙인다
    }
  };
  ws.onerror = () => onError?.("network");

  return function stop() {                                            // 말하기 끝
    processor.disconnect(); source.disconnect(); stream.getTracks().forEach((t) => t.stop()); ctx.close();
    if (ws.readyState === WebSocket.OPEN) ws.send(audioEvent(new Uint8Array(0)));  // 빈 AudioEvent = 스트림 끝
    setTimeout(() => ws.close(), 1500);                               // 마지막 확정 결과를 받을 시간
  };
}
```

주의
- 마이크는 HTTPS(CloudFront) 또는 `localhost` 에서만 열린다.
- `AudioContext({sampleRate: 16000})` 를 Firefox 가 마이크와 연결하지 못하면, 기본 샘플레이트로 받아 16kHz 로 다운샘플링해서 보낸다.
- 녹음마다 `/voice/url` 을 새로 부른다 (URL 재사용 불가). 동시에 열 수 있는 스트림 수는 계정 할당량을 따른다.
- 오류 `:exception-type`: `BadRequestException`(형식·샘플레이트 불일치), `LimitExceededException`(동시 스트림 초과), `UnrecognizedClientException`(서명 만료 등 → 새 URL).

## 4. 채팅 연결 (필수 범위)

1. 🎤 버튼 → `startVoiceInput({ language: profile.language, ... })`
2. `onPartial` 은 입력창에 회색으로 보여 주고, `onFinal` 문장을 이어 붙여 입력창 값으로 둔다.
3. 사용자가 확인하고 보내기 → 기존 `POST /chat`:
   ```json
   { "session_id": "...", "plan_id": "...", "message": "<인식된 문장>", "profile": { "language": "ja", "...": "..." } }
   ```
   `profile.language` 는 녹음에 쓴 `language` 와 같게 둔다 (결과 문장 언어와 답변 언어가 같아진다).
4. 장면 1 데모 캐시는 대본 문장과 정확히 같을 때만 쓰인다. 음성 인식 문장은 문장부호·한자가 달라질 수 있으므로, 시연 장면 1은 입력창에서 대본 문장을 붙여 넣는다.

## 5. 음성 번역으로 넓힐 때 (이번 범위 아님)

음성 → 문장은 위와 같다. 그 문장과 결과 문장 언어(`backend/app/voice/languages.py` 의 `transcript_language`)를 번역 모듈에 넘기면 된다.
번역 API(Bedrock)는 아직 없다. 추가할 때는 계약(`docs/api-contract.md`)에 경로를 먼저 올리고, `app/voice` 는 바꾸지 않는다.
사진 번역(`/photo/translate`, Textract + Bedrock)은 그대로 둔다.

## 6. 시간이 부족할 때의 최소 동작

- **A안 (권장, AWS):** 위 3절 그대로, 중간 결과 표시 없이 `onFinal` 만 입력창에 넣는다. 서버 쪽은 완료되어 있다.
- **B안 (대체):** 브라우저 Web Speech API(`SpeechRecognition`, Chrome·Edge·Safari)로 받아 같은 입력창·`/chat` 에 넣는다.
  번역 화면(`TranslationPage.jsx`)이 이미 쓰는 방식이라 바로 쓸 수 있다. AWS Transcribe 를 쓰지 않으므로 발표에서는 대체 방식이라고 밝힌다.
