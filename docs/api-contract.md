# API 계약 v0.1

> **변경 규칙**: 이 문서는 공용 파일이다. 뼈대 담당자 리뷰를 거친 PR로만 바꾼다.
> 바꿀 때는 `backend/app/models/` 의 모델, `backend/app/data/` 의 샘플, 프론트엔드 mock 복사본을 같은 PR에서 함께 맞춘다.

- 모든 요청·응답은 `application/json`, UTF-8.
- 필드 이름과 타입은 `backend/app/models/plan.py`(데이터)와 `backend/app/models/api.py`(요청·응답)의 Pydantic 모델과 같다.
  아래에서 `Plan`, `Place`, `Stop`, `Issue`, `RepairOption`, `StopChange` 는 그 모델을 가리킨다.
- 시각은 시간대를 포함한 ISO 8601 (`2026-11-21T10:00:00+09:00`), 날짜는 `YYYY-MM-DD`.
- `POST /chat` 은 스트리밍으로 응답한다(11/20 결정). 이벤트 형식은 금 12:00 점검 1에서 확정해 이 문서에 추가한다. 확정 전까지는 아래 `ChatResponse` 를 한 번에 돌려준다.
- 나머지 경로는 스트리밍하지 않는다. 응답은 한 번에 온다.
- 아래 예시는 `backend/app/data/` 의 샘플과 같은 내용이다. 실제 응답 전체는
  `uv run python -m scripts.local_invoke` 로 볼 수 있다.

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
      "issue_id": "i1",
      "type": "crowded",
      "stop_id": "s1",
      "severity": "medium",
      "detail": "토요일 혼잡 예상(요일 규칙)"
    },
    {
      "issue_id": "i2",
      "type": "rain",
      "stop_id": "s4",
      "severity": "high",
      "detail": "15:00-18:00 강수확률 80%, 실외 장소"
    }
  ],
  "repairs": {
    "i1": [
      {
        "action": "move_time",
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
            "after": {
              "stop_id": "s1",
              "place_id": "gamcheon-village",
              "start": "2026-11-21T09:00:00+09:00",
              "end": "2026-11-21T10:30:00+09:00",
              "locked": false
            }
          }
        ],
        "metrics": { "changed": 0, "kept": 4, "extra_travel_min": 0, "locked_kept": true }
      }
    ],
    "i2": [
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

- `checked_at`: 점검 기준 시각. `DEMO_NOW` 가 설정돼 있으면 그 값.
- `issues`: `Issue` 목록. `type` 은 `crowded` / `rain` / `closed` / `tight_transfer`, `severity` 는 `low` / `medium` / `high`. 문제가 없으면 `[]`.
- `repairs`: `issue_id` → `RepairOption` 목록. 변경이 작은 순서 (시간 이동 → 순서 변경 → 교체 → 제외).
  `action` 은 `move_time` / `reorder` / `replace` / `remove`.
- `metrics.changed` 는 장소가 교체·제거된 Stop 수다. 시각·순서만 바뀐 Stop 은 세지 않는다 (시간만 옮긴 해결안은 `changed: 0`).
  시각이 바뀐 Stop 은 모두 `changes` 에 들어 있다.
- `places`: `repairs` 에 새로 등장하는 장소의 `Place` 목록 (교체 후보 표시용). 없으면 `[]`.
- 해결안을 적용하려면 프론트엔드가 `changes` 를 일정에 반영해 `PUT /plan/{plan_id}` 로 저장한다.
