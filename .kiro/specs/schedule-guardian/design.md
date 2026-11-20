# 설계: Schedule Guardian

형식(`Plan`, `Stop`, `Issue`, `RepairOption`, `StopChange`, `PreservationMetrics`)과 API는 `docs/api-contract.md`, `backend/app/models/plan.py`를 따릅니다. 이 문서에는 내부 구조와 규칙만 적습니다.

## 구성
```
backend/app/guardian/
  check.py      check_plan(plan, context) -> list[Issue]       (뼈대에 시그니처 있음)
  repair.py     propose_repairs(plan, issue, context) -> list[RepairOption]  (뼈대에 시그니처 있음)
  context.py    CheckContext 모델과 조립 함수 (새로 추가)
  rules.py      문제 유형별 점검 함수 4개 (새로 추가)
  metrics.py    보전 지표 계산 (새로 추가)
  thresholds.py 기준값 상수 (새로 추가)
```
- `guardian/`은 boto3·HTTP를 직접 부르지 않습니다. 외부 데이터는 `context`로 받습니다.
- `context` 조립(도구 호출)은 `context.py`의 `build_context(plan)` 한 곳에서 합니다. 여기서만 `app/tools/` 조회 함수를 부릅니다.
- `handler.py`의 `POST /plan/check`가 `build_context` → `check_plan` → Issue마다 `propose_repairs`를 호출해 `CheckResponse`를 만듭니다. 이 연결은 공용 파일 수정이라 별도 PR로 올립니다.

## context 형식 (`context.py`)
`check_plan`의 `context: dict`를 Pydantic 모델로 정합니다. 모델은 `guardian/` 안에 두므로 공용 모델(`app/models/`)을 바꾸지 않습니다.

| 필드 | 내용 |
|---|---|
| `now` | 점검 기준 시각 (`DEMO_NOW` 또는 현재 시각) |
| `places` | `place_id` → `Place` (`places.json`) |
| `weather` | 시간대별 강수확률·강수 형태 (`get_weather` 결과, 없으면 `None`) |
| `crowd` | `place_id` → 혼잡 정도 (`get_crowd` 결과) |
| `hours` | `place_id` → 운영시간·휴무일 (없으면 빠짐) |
| `travel_min` | `(from_place_id, to_place_id)` → 이동 시간(분) |
| `events` | 방문일 행사 목록 |

도구 반환 형식은 11/20에 정했습니다(`.kiro/specs/chat-agent/design.md` 「조회 도구 반환 형식」). `build_context`는 그 결과를 이 표의 필드로 옮깁니다. `get_crowd`의 `ratio`가 `null`이면(`source: "weekday_rule"`) `crowd`에 넣지 않고 요일 규칙으로 판단합니다.
`demo.now`가 있으면 `now`에, `demo.weather_preset`이 있으면 `backend/app/data/weather/{이름}.json`을 `weather`에 넣습니다.

## 기준값 (`thresholds.py`)
리허설 전에 데모 데이터로 맞추고 고정합니다.

| 이름 | 초기값 | 뜻 |
|---|---|---|
| `CROWD_MEDIUM_RATE` | 85 | 집중률이 이 값 이상이면 `medium` |
| `CROWD_HIGH_RATE` | 95 | 집중률이 이 값 이상이고 주말이면 `high` |
| `WEEKDAY_RULE_PLACES` | `gamcheon-village`, `haedong-yonggungsa` | 집중률에 없는 장소. 토 `medium`, 일 `low` |
| `RAIN_POP_MEDIUM` | 60 | 체류 시간대 최대 강수확률(%)이 이 값 이상이면 `medium` |
| `RAIN_PTY_HIGH_RATIO` | 0.5 | 체류 시간의 50% 이상에 강수가 있으면 `high` |
| `TRANSFER_BUFFER_MIN` | 10 | 이동 여유(분). 미만이면 `medium`, 0 미만이면 `high` |
| `MIN_DWELL_MIN` | 45 | 체류 시간 축소 하한(분) |
| `SHIFT_STEPS_MIN` | 30, 60, 90 | `move_time` 시도 폭(분) |
| `REPLACE_MAX_EXTRA_MIN` | 30 | `replace` 이동 시간 증가 상한(분) |
| `MAX_REPAIRS` | 3 | Issue당 해결안 수 |

`WEEKDAY_RULE_PLACES`의 ID는 `places.json`에 있는 값만 씁니다. 흰여울문화마을 등이 추가되면 함께 넣습니다.

## 점검 규칙 (`rules.py`)
| 함수 | 판정 |
|---|---|
| `check_crowded(stop, ctx)` | 집중률 기준 또는 요일 규칙 → 행사일이면 한 단계 올림 |
| `check_rain(stop, ctx)` | 실외 장소만. 체류 시간대 최대 강수확률과 강수 비율로 판정. 예보 없으면 건너뜀 |
| `check_closed(stop, ctx)` | 휴무일 또는 운영시간 밖이면 `high`. 영업 정보 없으면 건너뜀 |
| `check_tight_transfer(prev, stop, ctx)` | `stop.start - (prev.end + travel_min) < TRANSFER_BUFFER_MIN` |

- `issue_id`: `{stop_id}-{type}` (예: `s4-rain`). 같은 일정·같은 문제면 항상 같은 값입니다.
- 고정 일정의 Issue는 `severity`를 `low`로 낮춥니다.
- `detail` 예: `"토요일 요일 규칙, 집중률 데이터 없음"`, `"15:30-17:00 최대 강수확률 80%, 강수 시간 100%, 실외 장소"`
- 정렬: `severity` 높은 순, 같으면 Stop `start` 이른 순.

## 해결안 탐색 (`repair.py`)
```
propose_repairs(plan, issue, ctx) -> list[RepairOption]
  if 대상 Stop이 locked: return []
  options  = try_move_time(...)   # 1단계
  options += try_reorder(...)     # 2단계
  options += try_replace(...)     # 3단계
  if not options: options = try_remove(...)  # 4단계
  valid = [o for o in options if o.metrics.locked_kept and not same_high_issue_remains(o)]
  return sorted(valid, key=(changed, extra_travel_min, 단계 순서))[:MAX_REPAIRS]
```

### 1단계 `move_time`
- 대상 Stop의 `start`·`end`를 `SHIFT_STEPS_MIN` 폭으로 앞뒤로 옮깁니다.
- 자리가 모자라면 이웃한 비고정 Stop의 체류 시간을 `MIN_DWELL_MIN`까지 늘이거나 줄입니다.
- `crowded`에는 행사 시간대 근거가 있을 때만 만듭니다.

### 2단계 `reorder`
- 대상 Stop과 이웃한 비고정 Stop의 순서를 바꾸고 시각을 다시 계산합니다.
- 이동 시간 증가가 `REPLACE_MAX_EXTRA_MIN`을 넘으면 뺍니다.

### 3단계 `replace`
- 후보: 같은 `category`인 장소. `rain`이면 `indoor: true`인 장소를 먼저 봅니다.
- 조건: 이동 시간 증가 30분 이하, 바꾼 뒤 같은 유형 `high` Issue 없음. 시각은 그대로 둡니다.

### 4단계 `remove`
- 대상 Stop을 뺍니다. 다른 단계 해결안이 없을 때만 돌려줍니다.

### StopChange 만들기
- 바뀐 Stop마다 `StopChange(stop_id, before, after)`를 만듭니다. `remove`는 `after: null`입니다.
- `reorder`는 시각이 바뀐 Stop 모두를 `changes`에 넣습니다.

## 보전 지표 (`metrics.py`)
| 필드 | 계산 |
|---|---|
| `changed` | 장소가 교체·제거된 Stop 수. 시각·순서만 바뀐 Stop은 세지 않습니다 |
| `kept` | 원래 `place_id` 중 새 일정에 남은 수 |
| `extra_travel_min` | 새 일정 총 이동 시간 − 원래 총 이동 시간 (음수 가능) |
| `locked_kept` | 모든 고정 Stop의 `place_id`·`start`·`end`가 같으면 `true` |

화면 문구 예: `changed=0`이고 시각만 바뀌면 "변경 0곳 · 시간만 조정"으로 표시합니다.

## 지연 재조정 (요구사항 7)
- 입력: 일정, 지연 시간(분), `context`. 대상은 기준 시각(`context.now`)에 아직 끝나지 않은(`end > now`) 비고정 Stop입니다. 이미 끝난 Stop과 고정 Stop은 그대로 둡니다.
- 탐색 단계 순서는 `propose_repairs`와 같습니다(시간 이동 → 순서 변경 → 교체 → 제외). 어느 안이든 바꾼 뒤 시각은 `move_time`과 같은 미루기 규칙(`delay_shift`)으로 다시 배치합니다.
  - `move_time`: 첫 대상 Stop을 지연만큼 미루고, 뒤 Stop은 이동 시간 + 여유가 모자랄 때만 필요한 만큼 미룹니다. 고정 일정 앞에서 모자라면 고정 일정에 가까운 Stop부터 `MIN_DWELL_MIN`까지 체류 시간을 줄입니다.
  - `reorder`·`replace`: `move_time`이 안 될 때만 찾습니다. 이웃한 대상 Stop 순서 바꾸기, 같은 `category` 장소로 바꾸기. 이동 시간을 모르거나 증가가 `REPLACE_MAX_EXTRA_MIN`을 넘으면 뺍니다.
  - `remove`: 대상 Stop 하나를 뺍니다. **`move_time`이 되더라도 함께 제시합니다** (노션 데모 대본 장면 6: 체류를 줄이는 안(변경 0곳) 다음에 1곳 빼는 안(변경 1곳)). `propose_repairs`의 "제외는 다른 해결안이 없을 때만"(요구사항 4.9)과 다른 점입니다. 이동 시간을 모르는 구간이 생기면 뺍니다.
- 공통 조건: 고정 일정 유지, 재배치 후 원래 없던 `high` Issue(운영시간 밖 등)가 없을 것, 방문일 안.
- 정렬: `changed` → `extra_travel_min` → 단계 순서, 상위 `MAX_REPAIRS`개.
- 출력: `RepairOption` 목록과 보전 지표. API는 `POST /plan/{plan_id}/delay`(`DelayRequest` → `DelayResponse`, `docs/api-contract.md`)입니다.
- 함수: `guardian/delay.py`의 `propose_delay_repairs(plan, delay_min, ctx) -> list[RepairOption]`. `handler.py` 연결은 A와 따로 PR로 올립니다.

## 예약 점검 (요구사항 8)
```
EventBridge Scheduler (예보 갱신 시각)
  → 점검 Lambda: 저장된 일정 읽기 → build_context → check_plan (LLM 없음)
  → 결과를 DynamoDB에 저장 → /alerts API가 읽어 배지로 표시
```
- 점검 로직은 `guardian/scheduled.py`(D)에 둡니다. Lambda 연결과 EventBridge 스케줄은 `infra/`(A)에서 하고, DynamoDB 저장 형식은 세션 저장 담당(A)과 정합니다.

## 오류 처리
- `context`에 필요한 값이 없으면 그 규칙만 건너뜁니다. 점검 전체를 실패시키지 않습니다.
- 날씨 예보가 없는 날짜(약 3일 이후)는 `rain` 규칙을 건너뜁니다.

## 테스트 (`backend/tests/test_guardian.py`)
`backend/app/data/sample_plan.json`(11/21 토, 4곳, 자갈치시장 고정)과 손으로 만든 `context`로 돌립니다.

| 케이스 | 기대 결과 |
|---|---|
| 토요일 감천문화마을 10:00 | `crowded` `medium` (요일 규칙) |
| 15~18시 강수확률 80%, 해운대 15:30 | `rain` `high`, 첫 해결안 `replace` → 실내 장소, `locked_kept: true` |
| 13~15시 비, 부산타워 실내 | 부산타워 Issue 없음 |
| 고정 일정(자갈치시장) 휴무 | `closed` `low`, 해결안 없음 |
| 이동 시간 40분, 간격 30분 | `tight_transfer` `high` |
| 같은 입력 두 번 | `issue_id` 같음 |
| 모든 해결안 | 자갈치시장 `place_id`·`start`·`end` 그대로 |
