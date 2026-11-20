"""음성 입력 실환경 점검 (A). 브라우저 없이 /voice/url → Transcribe Streaming(WebSocket) → /chat 을 차례로 확인한다.

    # 1) AWS 없이: EventStream 인코딩을 AWS SDK(botocore) 디코더로 왕복 검증 + 테스트 음성(WAV) 만들기
    uv run python -m scripts.voice_stream_check --self-check
    uv run python -m scripts.voice_stream_check --make-wav ../voice_ja.wav --text "明日、海雲台に行きたいです。"
    # 2) 배포 API 로 실제 점검 (자격 증명 불필요. /voice/url 은 Lambda 실행 역할이 서명한다)
    uv run --with websockets python -m scripts.voice_stream_check --api <Function URL> --wav ../voice_ja.wav

- 오디오: 16kHz, 16비트 PCM(리틀 엔디언), 모노 WAV (/voice/url 의 sample_rate·media_encoding 과 같아야 한다).
  --make-wav 는 Windows 기본 일본어 음성(Microsoft Haruka)으로 만든다.
- 프로토콜: https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html
  오디오 조각마다 AudioEvent 이벤트 스트림 메시지(헤더 :content-type·:event-type·:message-type + CRC32)를 보내고,
  끝에는 빈 AudioEvent 를 보낸다. 응답은 TranscriptEvent(JSON) 또는 exception 메시지다.
- 서명 URL·세션 토큰·키는 출력하지 않는다. URL 은 호스트·언어 코드·서명 존재 여부만 확인해 보여 준다.
- 실제 마이크 입력과 브라우저 화면은 프론트엔드(C) 담당이라 여기서 다루지 않는다.
"""

import argparse
import asyncio
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
import zlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from botocore.eventstream import EventStreamBuffer

CHUNK_MS = 100  # 오디오 조각 길이. 실제 시간보다 2배 빠르게 보낸다 (PACE)
PACE = 0.5
FINISH_WAIT_SEC = 10  # 빈 AudioEvent 를 보낸 뒤 마지막 결과를 기다리는 시간
HTTP_TIMEOUT_SEC = 60


# ---- EventStream (AWS 이벤트 스트림 인코딩) ----


def _string_header(name: str, value: str) -> bytes:
    name_b, value_b = name.encode(), value.encode()
    return struct.pack("!B", len(name_b)) + name_b + struct.pack("!BH", 7, len(value_b)) + value_b  # 7 = string


def audio_event(chunk: bytes) -> bytes:
    """AudioEvent 메시지 하나: prelude(전체 길이, 헤더 길이) + prelude CRC + 헤더 + 오디오 + 메시지 CRC."""
    headers = (_string_header(":content-type", "application/octet-stream")
               + _string_header(":event-type", "AudioEvent")
               + _string_header(":message-type", "event"))
    total = 4 + 4 + 4 + len(headers) + len(chunk) + 4
    prelude = struct.pack("!II", total, len(headers))
    message = prelude + struct.pack("!I", zlib.crc32(prelude)) + headers + chunk
    return message + struct.pack("!I", zlib.crc32(message))


def decode_messages(buffer: EventStreamBuffer, data: bytes) -> list[tuple[dict, bytes]]:
    """받은 바이트를 AWS SDK 디코더로 메시지 (헤더, 본문) 목록으로 바꾼다. CRC 가 틀리면 예외."""
    buffer.add_data(data)
    return [(message.headers, message.payload) for message in buffer]


def self_check() -> int:
    """AWS 없이: 우리 인코더가 만든 메시지를 botocore 디코더가 같은 헤더·본문으로 읽는지 확인한다."""
    for payload in (b"", b"\x01\x02" * 1600, os.urandom(3200)):
        [(headers, body)] = decode_messages(EventStreamBuffer(), audio_event(payload))
        expected = {":content-type": "application/octet-stream", ":event-type": "AudioEvent", ":message-type": "event"}
        assert headers == expected, headers
        assert body == payload
    print("self-check: AudioEvent 인코딩이 AWS SDK(botocore) 디코더와 맞습니다 (빈 조각, 3200바이트 조각 2종).")
    return 0


# ---- 테스트 음성 ----


def make_wav(path: Path, text: str, sample_rate: int = 16000) -> int:
    """Windows 일본어 음성으로 16kHz·16비트·모노 WAV 를 만든다 (PowerShell System.Speech)."""
    if sys.platform != "win32":
        print("--make-wav 는 Windows 에서만 됩니다. 16kHz 16비트 모노 WAV 를 직접 준비해 --wav 로 넘겨 주세요.")
        return 2
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1; "
        "if (-not $v) { exit 3 }; $s.SelectVoice($v.VoiceInfo.Name); "
        f"$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({sample_rate}, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        "$s.SetOutputToWaveFile($env:VOICE_WAV_PATH, $f); $s.Speak($env:VOICE_WAV_TEXT); $s.Dispose()"
    )
    env = {**os.environ, "VOICE_WAV_PATH": str(path.resolve()), "VOICE_WAV_TEXT": text}
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, capture_output=True, text=True)
    if result.returncode == 3:
        print("일본어(ja-JP) 음성이 설치되어 있지 않습니다.")
        return 3
    if result.returncode != 0:
        print("WAV 를 만들지 못했습니다:", result.stderr.strip()[:300])
        return 1
    rate, seconds = read_pcm(path)[1:]
    print(f"WAV 생성: {path.name} ({rate}Hz, 16비트, 모노, {seconds:.1f}초) 문장: {text}")
    return 0


def read_pcm(path: Path) -> tuple[bytes, int, float]:
    """WAV 의 PCM 바이트, 샘플레이트, 길이(초). 16비트 모노가 아니면 SystemExit."""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise SystemExit(f"{path.name}: 16비트 모노 WAV 여야 합니다 (현재 {wav.getsampwidth() * 8}비트 {wav.getnchannels()}채널).")
        frames = wav.readframes(wav.getnframes())
        return frames, wav.getframerate(), wav.getnframes() / wav.getframerate()


# ---- API ----


def post(api: str, path: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        api.rstrip("/") + path, data=json.dumps(body, ensure_ascii=False).encode(), method="POST",
        headers={"content-type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SEC) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


def describe_url(url: str) -> str:
    """서명 URL 을 출력하지 않고 확인한 것만 적는다."""
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return (f"scheme={parts.scheme} host={parts.hostname} port={parts.port} path={parts.path} "
            f"language-code={query.get('language-code', ['?'])[0]} sample-rate={query.get('sample-rate', ['?'])[0]} "
            f"signed={'X-Amz-Signature' in query} session-token={'X-Amz-Security-Token' in query}")


# ---- Transcribe Streaming ----


async def stream(url: str, pcm: bytes, sample_rate: int) -> dict:
    """오디오를 보내고 확정 문장과 오류를 모은다."""
    import websockets  # uv run --with websockets 로만 쓴다 (프로젝트 의존성이 아니다)

    finals: list[str] = []
    partials = 0
    errors: list[str] = []
    chunk_bytes = sample_rate * 2 * CHUNK_MS // 1000
    buffer = EventStreamBuffer()
    started = time.perf_counter()
    first_result: float | None = None

    async with websockets.connect(url, max_size=None, open_timeout=10, ping_interval=None) as ws:
        async def send() -> None:
            for offset in range(0, len(pcm), chunk_bytes):
                await ws.send(audio_event(pcm[offset:offset + chunk_bytes]))
                await asyncio.sleep(CHUNK_MS / 1000 * PACE)
            await ws.send(audio_event(b""))  # 스트림 끝

        async def receive() -> None:
            nonlocal partials, first_result
            async for data in ws:
                for headers, body in decode_messages(buffer, data):
                    kind = headers.get(":message-type")
                    if kind == "exception":
                        errors.append(f"{headers.get(':exception-type')}: {json.loads(body or b'{}').get('Message', '')}")
                        continue
                    for result in json.loads(body).get("Transcript", {}).get("Results", []):
                        text = (result.get("Alternatives") or [{}])[0].get("Transcript", "")
                        if first_result is None:
                            first_result = time.perf_counter() - started
                        if result.get("IsPartial"):
                            partials += 1
                        elif text:
                            finals.append(text)

        receiver = asyncio.create_task(receive())
        await send()
        try:
            await asyncio.wait_for(receiver, timeout=FINISH_WAIT_SEC)
        except TimeoutError:
            receiver.cancel()
    return {"finals": finals, "partials": partials, "errors": errors,
            "first_result_sec": first_result, "total_sec": time.perf_counter() - started}


def run(api: str, wav: Path, language: str) -> int:
    pcm, rate, seconds = read_pcm(wav)

    status, voice = post(api, "/voice/url", {"language": language})
    print(f"[1] POST /voice/url → {status}")
    if status != 200:
        print("    오류:", voice.get("error"))
        return 1
    print("    " + describe_url(voice["url"]))
    print(f"    expires_in={voice['expires_in']} sample_rate={voice['sample_rate']} media_encoding={voice['media_encoding']}")
    if "mock-transcribe.invalid" in voice["url"]:
        print("    USE_MOCK=1 서버라 실제 Transcribe 에 연결할 수 없습니다. 배포 API 주소로 다시 실행해 주세요.")
        return 2
    if rate != voice["sample_rate"] or voice["media_encoding"] != "pcm":
        print(f"    WAV 샘플레이트({rate})가 서명 값({voice['sample_rate']})과 다릅니다.")
        return 1

    print(f"[2] Transcribe Streaming 연결, 음성 {seconds:.1f}초 전송")
    result = asyncio.run(stream(voice["url"], pcm, rate))
    transcript = "".join(result["finals"]).strip()
    print(f"    확정 문장 {len(result['finals'])}개, 중간 결과 {result['partials']}개, "
          f"첫 결과 {result['first_result_sec'] or 0:.1f}초, 전체 {result['total_sec']:.1f}초")
    for error in result["errors"]:
        print("    Transcribe 오류:", error)
    print(f"    인식 결과: {transcript or '(없음)'}")
    if not transcript:
        return 1

    print("[3] POST /chat (인식된 문장)")
    started = time.perf_counter()
    status, chat = post(api, "/chat", {"message": transcript, "profile": {"language": language}})
    print(f"    → {status} ({time.perf_counter() - started:.1f}초)")
    if status != 200:
        print("    오류:", chat.get("error"))
        return 1
    print(f"    language={chat['language']} plan_changes={len(chat['plan_changes'])} sources={len(chat['sources'])} "
          f"score_breakdown={'있음' if chat.get('score_breakdown') else '없음'}")
    print("    answer:", chat["answer"][:200])
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="음성 입력 실환경 점검 (/voice/url → Transcribe → /chat)")
    parser.add_argument("--api", default=os.environ.get("BUSAN_API_URL", ""), help="API 주소 (기본: 환경 변수 BUSAN_API_URL)")
    parser.add_argument("--wav", type=Path, help="16kHz 16비트 모노 WAV")
    parser.add_argument("--language", default="ja", choices=["en", "ja", "zh-Hans", "zh-Hant"])
    parser.add_argument("--make-wav", type=Path, help="Windows 일본어 음성으로 테스트 WAV 를 만든다")
    parser.add_argument("--text", default="明日、海雲台に行きたいです。おすすめの場所を教えてください。")
    parser.add_argument("--self-check", action="store_true", help="AWS 없이 EventStream 인코딩만 확인")
    args = parser.parse_args(argv)

    if args.self_check:
        return self_check()
    if args.make_wav:
        return make_wav(args.make_wav, args.text)
    if not args.api or not args.wav:
        parser.error("--api(또는 BUSAN_API_URL)와 --wav 가 필요합니다.")
    return run(args.api, args.wav, args.language)


if __name__ == "__main__":
    sys.exit(main())
