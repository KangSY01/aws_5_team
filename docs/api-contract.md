# API 계약 v0.2

> **변경 규칙**: 이 문서는 공용 파일이다. 뼈대 담당자 리뷰를 거친 PR로만 바꾼다.
> 바꿀 때는 `backend/app/models/` 의 모델, `backend/app/data/` 의 샘플, 프론트엔드 mock 복사본을 같은 PR에서 함께 맞춘다.

- 모든 요청·응답은 `application/json`, UTF-8. 예외는 `POST /chat` 스트리밍 응답(`text/event-stream`)뿐이다.
- 필드 이름과 타입은 `backend/app/models/plan.py`(데이터)와 `backend/app/models/api.py`(요청·응답)의 Pydantic 모델과 같다.
  아래에서 `Plan`, `Place`, `Stop`, `Issue`, `RepairOption`, `StopChange` 는 그 모델을 가리킨다.
- 시각은 시간대를 포함한 ISO 8601 (`2026-11-21T10:00:00+09:00`), 날짜는 `YYYY-MM-DD`.
- `POST /chat` 만 스트리밍한다(SSE, 아래 「스트리밍」). 나머지 경로는 응답이 한 번에 온다.
- 기존 경로(`/chat`, `/plan`, `/plan/check`)의 예시는 `backend/app/data/` 의 샘플과 같은 내용이다. 실제 응답 전체는
  `uv run python -m scripts.local_invoke` 로 볼 수 있다.
- 「v0.2 추가 경로」의 경로는 아직 `handler.py` 에 없다. 각 담당자가 구현할 때 고정 응답 샘플과 함께 `handler.py` 연결 PR을 올린다.
  그 전까지 예시는 `backend/tests/test_contract.py` 가 모델과 맞는지만 확인한다.

## 데모 스위치

`POST /chat`, `POST /plan/check`, `POST /plan/{plan_id}/delay` 요청에 `demo` 를 넣으면 그 요청에서만 기준 시각과 날씨를 바꾼다. 생략하거나 `null` 이면 평소대로 동작한다.

```json
{ "now": "2026-11-28T13:00:00+09:00", "weather_preset": "rain-afternoon" }
```

- `now`: 점검 기준 시각. 없으면 `DEMO_NOW`, 그것도 없으면 현재 시각.
- `weather_preset`: `backend/app/data/weather/{이름}.json` 샘플 예보의 이름. 없는 이름이면 `422 validation_error`.

## 오류 형식

모든 엔드포인트 공통. HTTP 상태 코드와 함께 반환한다.

```json
{ "error": { "code": "plan_not_found", "message": "plan-9 을 찾을 수 없습니다." } }
```

| 상태 | code | 뜻 |
|---|---|---|
| 400 | `bad_request` | 본문이 올바른 JSON이 아님 |
| 404 | `not_found` | 없는 경로 또는 메서드 |
| 404 | `plan_not_found` | 없는 plan_id |
| 422 | `validation_error` | 모델 검증 실패 (필드 누락, 경로와 다른 plan_id, 알 수 없는 place_id 등) |
| 500 | `internal_error` | 서버 오류 |

## POST /chat

사용자 메시지 한 건을 에이전트에 보낸다.
첫 메시지라 세션이나 일정이 아직 없으면 `session_id`, `plan_id` 를 `null` 로 보내거나 생략한다. 서버가 새로 발급해 응답에 넣는다.

요청

```json
{
  "session_id": "sess-1",
  "plan_id": "plan-1",
  "message": "午後は雨みたいなので、屋内の場所に変えてください",
  "profile": {
    "language": "ja",
    "interests": ["food", "sea"],
    "companions": "couple",
    "diet": [],
    "budget": "mid"
  }
}
```

응답

```json
{
  "session_id": "sess-1",
  "plan_id": "plan-1",
  "answer": "午後は雨の予報のため、海雲台海水浴場を屋内の新世界百貨店センタムシティに変更しました。",
  "language": "ja",
  "sources": [
    { "tool": "get_weather", "id": "busan-2026-11-21", "title": "부산 단기예보" },
    { "tool": "search_places", "id": "shinsegae-centum-city", "title": "新世界百貨店センタムシティ" }
  ],
  "plan_changes": [
    {
      "stop_id": "s4",
      "before": {
        "stop_id": "s4",
        "place_id": "haeundae-beach",
        "start": "2026-11-21T15:30:00+09:00",
        "end": "2026-11-21T17:00:00+09:00",
        "locked": false
      },
      "after": {
        "stop_id": "s4",
        "place_id": "shinsegae-centum-city",
        "start": "2026-11-21T15:30:00+09:00",
        "end": "2026-11-21T17:00:00+09:00",
        "locked": false
      }
    }
  ]
}
```

- `answer`: `language` 로 쓴 답변 문장.
- `sources`: 답변의 근거가 된 도구 결과. `tool` 은 도구 이름, `id` 는 그 도구 결과 안의 항목 ID, `title` 은 표시용 제목.
- `plan_changes`: 이번 응답에서 일정에 적용된 변경 (`StopChange` 목록). 변경이 없으면 `[]`.
  `before` 가 `null` 이면 추가, `after` 가 `null` 이면 제거.
- `plan_changes` 가 비어 있지 않으면 프론트엔드는 `GET /plan/{plan_id}` 로 일정을 다시 읽는다.

### 스트리밍

요청 헤더에 `Accept: text/event-stream` 이 있으면 SSE(Server-Sent Events)로 응답한다. 없으면 위 `ChatResponse` 를 한 번에 돌려준다(로컬 테스트·대체 경로).

```text
event: delta
data: {"text": "午後は雨の予報のため、"}

event: delta
data: {"text": "海雲台海水浴場を屋内の新世界百貨店センタムシティに変更しました。"}

event: done
data: {"session_id": "sess-1", "plan_id": "plan-1", "answer": "...", "language": "ja", "sources": [...], "plan_changes": [...]}
```

| 이벤트 | `data` | 뜻 |
|---|---|---|
| `delta` | `{"text": str}` (`ChatDelta`) | 답변 문장 조각. 도착 순서대로 이어 붙인다 |
| `done` | `ChatResponse` | 마지막 이벤트. `answer` 는 `delta` 를 모두 이어 붙인 문장과 같다 |
| `error` | `ErrorResponse` (`{"error": {"code", "message"}}`) | 처리 중 오류. 마지막 이벤트이며 일정은 바뀌지 않는다 |

- 스트림은 `done` 또는 `error` 하나로 끝난다. 둘 다 없이 연결이 끊기면 프론트엔드는 오류로 보고 `GET /plan/{plan_id}` 로 일정을 다시 읽는다.
- 요청 검증 오류(400·404·422)는 스트림을 열기 전에 위 「오류 형식」의 JSON 으로 답한다.
- `plan_changes` 는 `done` 에만 들어 있다. 일정 저장도 `done` 을 보내기 직전에 끝낸다.
- 배포 방식(AgentCore Runtime 또는 Lambda Web Adapter)은 금 12:00 점검 1에서 확인한다. 이벤트 형식은 어느 쪽이든 같다.

## GET /plan/{plan_id}

일정과, 그 일정이 참조하는 장소 정보를 돌려준다.

응답 (`places` 는 한 곳만 표시, 나머지 생략)

```json
{
  "plan": {
    "plan_id": "plan-1",
    "date": "2026-11-21",
    "profile": {
      "language": "ja",
      "interests": ["food", "sea"],
      "companions": "couple",
      "diet": [],
      "budget": "mid"
    },
    "stops": [
      {
        "stop_id": "s1",
        "place_id": "gamcheon-village",
        "start": "2026-11-21T10:00:00+09:00",
        "end": "2026-11-21T11:30:00+09:00",
        "locked": false
      },
      {
        "stop_id": "s2",
        "place_id": "jagalchi-market",
        "start": "2026-11-21T12:00:00+09:00",
        "end": "2026-11-21T13:00:00+09:00",
        "locked": true
      },
      {
        "stop_id": "s3",
        "place_id": "busan-tower",
        "start": "2026-11-21T13:30:00+09:00",
        "end": "2026-11-21T14:30:00+09:00",
        "locked": false
      },
      {
        "stop_id": "s4",
        "place_id": "haeundae-beach",
        "start": "2026-11-21T15:30:00+09:00",
        "end": "2026-11-21T17:00:00+09:00",
        "locked": false
      }
    ]
  },
  "places": [
    {
      "place_id": "gamcheon-village",
      "names": {
        "en": "Gamcheon Culture Village",
        "ja": "甘川文化村",
        "zh-Hans": "甘川文化村",
        "zh-Hant": "甘川文化村"
      },
      "lat": 35.0975,
      "lng": 129.0106,
      "category": "village",
      "indoor": false,
      "nearest_station": "Toseong"
    }
  ]
}
```

- `nearest_station` 은 가까운 역이 없으면 `null`.

## PUT /plan/{plan_id}

일정 전체를 저장한다 (사용자가 직접 순서·시간·`locked` 를 바꿨거나 해결안을 적용했을 때).

요청: `Plan` 한 개 (`GET` 응답의 `plan` 과 같은 형식). 본문의 `plan_id` 는 경로의 값과 같아야 한다.

응답: `GET /plan/{plan_id}` 와 같은 형식 (`plan`, `places`).

## POST /plan/check

Schedule Guardian 으로 일정을 점검한다. LLM 을 호출하지 않는다.

요청

```json
{ "plan_id": "plan-1" }
```

응답

```json
{
  "plan_id": "plan-1",
  "checked_at": "2026-11-21T09:00:00+09:00",
  "issues": [
    {
      "issue_id": "s4-rain",
      "type": "rain",
      "stop_id": "s4",
      "severity": "high",
      "detail": "15:30-17:00 최대 강수확률 80%, 강수 시간 100%, 실외 장소"
    },
    {
      "issue_id": "s1-crowded",
      "type": "crowded",
      "stop_id": "s1",
      "severity": "medium",
      "detail": "토요일 요일 규칙, 집중률 데이터 없음"
    }
  ],
  "repairs": {
    "s1-crowded": [
      {
        "action": "remove",
        "changes": [
          {
            "stop_id": "s1",
            "before": {
              "stop_id": "s1",
              "place_id": "gamcheon-village",
              "start": "2026-11-21T10:00:00+09:00",
              "end": "2026-11-21T11:30:00+09:00",
              "locked": false
            },
            "after": null
          }
        ],
        "metrics": { "changed": 1, "kept": 3, "extra_travel_min": -15, "locked_kept": true }
      }
    ],
    "s4-rain": [
      {
        "action": "replace",
        "changes": [
          {
            "stop_id": "s4",
            "before": {
              "stop_id": "s4",
              "place_id": "haeundae-beach",
              "start": "2026-11-21T15:30:00+09:00",
              "end": "2026-11-21T17:00:00+09:00",
              "locked": false
            },
            "after": {
              "stop_id": "s4",
              "place_id": "shinsegae-centum-city",
              "start": "2026-11-21T15:30:00+09:00",
              "end": "2026-11-21T17:00:00+09:00",
              "locked": false
            }
          }
        ],
        "metrics": { "changed": 1, "kept": 3, "extra_travel_min": 5, "locked_kept": true }
      }
    ]
  },
  "places": [
    {
      "place_id": "shinsegae-centum-city",
      "names": {
        "en": "Shinsegae Centum City",
        "ja": "新世界百貨店センタムシティ",
        "zh-Hans": "新世界百货Centum City店",
        "zh-Hant": "新世界百貨Centum City店"
      },
      "lat": 35.1687,
      "lng": 129.1296,
      "category": "shopping",
      "indoor": true,
      "nearest_station": "Centum City"
    }
  ]
}
```

- 요청에 `demo`(「데모 스위치」)를 넣을 수 있다.
- `checked_at`: 점검 기준 시각. `demo.now`, `DEMO_NOW`, 현재 시각 순으로 정한다.
- `issue_id`: `{stop_id}-{type}` (예: `s4-rain`). 같은 일정·같은 문제면 항상 같은 값이다. `GET /alerts` 도 같은 값을 쓴다.
- `issues`: `Issue` 목록. `type` 은 `crowded` / `rain` / `closed` / `tight_transfer`, `severity` 는 `low` / `medium` / `high`. 문제가 없으면 `[]`.
- `repairs`: `issue_id` → `RepairOption` 목록. 변경이 작은 순서 (시간 이동 → 순서 변경 → 교체 → 제외).
  `action` 은 `move_time` / `reorder` / `replace` / `remove`.
- `crowded` 는 집중률·요일 규칙이 하루 단위라, 행사 시간대처럼 시간대 근거가 있을 때만 `move_time` 해결안이 나온다.
  위 예시의 `s1-crowded`(요일 규칙)은 시간 이동 근거가 없고, 이웃이 고정 일정이라 순서를 바꿀 수 없고, 같은 분류 장소(`huinnyeoul-village`)도 요일 규칙 대상이라 토요일에는 혼잡이 그대로여서 `remove` 만 나온 경우다.
- `metrics.changed` 는 장소가 교체·제거된 Stop 수다. 시각·순서만 바뀐 Stop 은 세지 않는다 (시간만 옮긴 해결안은 `changed: 0`).
  시각이 바뀐 Stop 은 모두 `changes` 에 들어 있다.
- `places`: `repairs` 에 새로 등장하는 장소의 `Place` 목록 (교체 후보 표시용). 없으면 `[]`.
- 해결안을 적용하려면 프론트엔드가 `changes` 를 일정에 반영해 `PUT /plan/{plan_id}` 로 저장한다.

## v0.2 추가 경로

11/20 결정. 담당은 `CONTRIBUTING.md` 「담당 영역」을 따른다. 아직 `handler.py` 에 연결되지 않았다.

| 경로 | 용도 | 담당 |
|---|---|---|
| `POST /plan/{plan_id}/delay` | "늦었어요" 지연 재조정 | D(Guardian), A(연결) |
| `GET /alerts?plan_id=` | 예약 점검 결과 조회 | A(API·저장), D(점검 로직) |
| `POST /photo/upload-url` | 사진 업로드용 S3 presigned URL | D |
| `POST /photo/translate` | 사진 글자 인식·번역·매운맛 표시 | D |
| `POST /speak` | 음성 출력 (Polly) | B |
| `POST /voice/url` | 음성 입력용 Transcribe 스트리밍 URL | A |

### POST /plan/{plan_id}/delay

일정이 늦어졌을 때 기준 시각 이후의 비고정 Stop만 재조정한 해결안을 돌려준다. 일정을 저장하지 않는다. LLM 을 호출하지 않는다.

요청 (`DelayRequest`, 본문의 `plan_id` 는 경로의 값과 같아야 한다. `demo` 는 선택)

```json
{ "plan_id": "plan-1", "delay_min": 30 }
```

응답 (`DelayResponse`)

```json
{
  "plan_id": "plan-1",
  "now": "2026-11-21T13:40:00+09:00",
  "repairs": [
    {
      "action": "move_time",
      "changes": [
        {
          "stop_id": "s3",
          "before": {
            "stop_id": "s3",
            "place_id": "busan-tower",
            "start": "2026-11-21T13:30:00+09:00",
            "end": "2026-11-21T14:30:00+09:00",
            "locked": false
          },
          "after": {
            "stop_id": "s3",
            "place_id": "busan-tower",
            "start": "2026-11-21T14:00:00+09:00",
            "end": "2026-11-21T15:00:00+09:00",
            "locked": false
          }
        }
      ],
      "metrics": { "changed": 0, "kept": 4, "extra_travel_min": 0, "locked_kept": true }
    }
  ],
  "places": []
}
```

- `now`: 재조정 기준 시각. `demo.now`, `DEMO_NOW`, 현재 시각 순.
- `delay_min`: 1~240. 범위를 벗어나면 `422 validation_error`.
- `repairs`: `/plan/check` 의 `repairs` 한 항목과 같은 형식, 같은 순서(시간 이동 → 순서 변경 → 교체 → 제외). 고칠 필요가 없으면 `[]`.
- `locked: true` 인 Stop 은 어떤 해결안에서도 바뀌지 않는다.
- 적용은 `/plan/check` 해결안과 같이 프론트엔드가 `PUT /plan/{plan_id}` 로 저장한다.
- `metrics.changed` 는 시간만 바뀐 Stop 을 세지 않는다(PR #12 기준).

### GET /alerts?plan_id=

예약 점검(EventBridge Scheduler → 점검 Lambda)이 저장한 마지막 점검 결과를 돌려준다. 점검을 새로 하지 않는다.

응답 (`AlertsResponse`)

```json
{
  "plan_id": "plan-1",
  "checked_at": "2026-11-21T11:10:00+09:00",
  "issues": [
    {
      "issue_id": "s4-rain",
      "type": "rain",
      "stop_id": "s4",
      "severity": "high",
      "detail": "15:30-17:00 최대 강수확률 80%, 강수 시간 100%, 실외 장소"
    }
  ]
}
```

- `plan_id` 쿼리가 없으면 `422 validation_error`, 없는 일정이면 `404 plan_not_found`.
- 아직 예약 점검을 하지 않았으면 `checked_at` 은 `null`, `issues` 는 `[]`.
- 해결안이 필요하면 프론트엔드가 `POST /plan/check` 를 호출한다.

### POST /photo/upload-url

사진을 S3 에 직접 올릴 presigned PUT URL 을 발급한다.

요청 (`PhotoUploadUrlRequest`, `content_type` 은 `image/jpeg` / `image/png`)

```json
{ "content_type": "image/jpeg" }
```

응답 (`PhotoUploadUrlResponse`)

```json
{
  "upload_url": "https://example-bucket.s3.ap-northeast-2.amazonaws.com/photos/abc123.jpg?X-Amz-Signature=...",
  "key": "photos/abc123.jpg",
  "expires_in": 300
}
```

- 프론트엔드는 `upload_url` 로 `PUT` 하고(헤더 `Content-Type` 은 요청한 값), 성공하면 `key` 로 `/photo/translate` 를 호출한다.

### POST /photo/translate

올린 사진의 한국어 글자를 읽어(Textract) 번역하고(Bedrock), 음식이면 매운맛 여부를 표시한다.

요청 (`PhotoTranslateRequest`)

```json
{ "key": "photos/abc123.jpg", "language": "ja" }
```

응답 (`PhotoTranslateResponse`)

```json
{
  "key": "photos/abc123.jpg",
  "language": "ja",
  "items": [
    {
      "text_ko": "돼지국밥",
      "translated": "テジクッパ（豚肉のスープご飯）",
      "bbox": { "left": 0.12, "top": 0.30, "width": 0.25, "height": 0.05 },
      "spicy": false
    },
    {
      "text_ko": "낙곱새",
      "translated": "ナッコプセ（タコ・ホルモン・エビの辛い鍋）",
      "bbox": { "left": 0.12, "top": 0.40, "width": 0.20, "height": 0.05 },
      "spicy": true
    }
  ]
}
```

- `bbox`: Textract `BoundingBox` 와 같은 기준. 사진 너비·높이 대비 비율(0~1). 프론트엔드는 사진 위에 겹쳐 그린다.
- `spicy`: 매운 음식이면 `true`, 아니면 `false`, 판단할 수 없으면 `null`. 번역 문장과 함께 "가게에 확인" 안내를 표시한다.
- 글자를 찾지 못하면 `items` 는 `[]`. 없는 `key` 면 `404 not_found`.

### POST /speak

문장을 음성(mp3)으로 바꾼다 (Polly). 현지인에게 보여주기 카드는 `language: "ko"`, 여행 중 음성 출력은 프로필 언어를 쓴다.

요청 (`SpeakRequest`, `text` 는 1~500자, `language` 는 `ko` / `en` / `ja` / `zh-Hans` / `zh-Hant`)

```json
{ "text": "자갈치시장까지 가는 버스를 타려면 어디로 가야 하나요?", "language": "ko" }
```

응답 (`SpeakResponse`)

```json
{ "content_type": "audio/mpeg", "audio_base64": "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjMuMTAw" }
```

- 프론트엔드는 `data:audio/mpeg;base64,{audio_base64}` 로 재생한다.

### POST /voice/url

브라우저가 Transcribe 스트리밍에 직접 연결할 WebSocket presigned URL 을 발급한다. 인식된 문장은 프론트엔드가 `POST /chat` 의 `message` 로 보낸다.

요청 (`VoiceUrlRequest`)

```json
{ "language": "ja" }
```

응답 (`VoiceUrlResponse`)

```json
{
  "url": "wss://transcribestreaming.ap-northeast-2.amazonaws.com:8443/stream-transcription-websocket?language-code=ja-JP&X-Amz-Signature=...",
  "expires_in": 300,
  "sample_rate": 16000,
  "media_encoding": "pcm"
}
```

- `language` 를 Transcribe 언어 코드로 바꾸는 일은 서버가 한다.
- 프론트엔드는 `sample_rate`, `media_encoding` 에 맞춰 마이크 오디오를 보낸다.
