# 평가 질의셋

담당: 이온규 (D). 원본 초안은 노션 「판단 단계 JSON · 시스템 프롬프트 · 평가 질의 (초안)」의 4장입니다.
이 저장소 구조(장소 ID, 도구 이름, API)에 맞게 옮긴 것이 `queries.json`입니다.

## 필드
| 필드 | 뜻 |
|---|---|
| `id` | 질의 번호 |
| `category` | `plan_create`, `plan_edit`, `recommend`, `place_detail`, `route`, `food`, `event`, `safety`, `guardian` |
| `endpoint` | `/chat` 또는 `/plan/check` |
| `plan_id` | 기존 일정 기준이면 `plan-1`, 새 대화면 `null` |
| `message`, `profile` | `ChatRequest`에 그대로 넣는 값 (`/plan/check`는 `null`) |
| `expect.tools` | 반드시 호출해야 하는 도구 |
| `expect.places_any` | 답변·`sources`·`plan_changes`에 나와야 하는 장소 ID (하나 이상) |
| `expect.checks` | 사람이 확인하는 통과 기준 |

## 채점 목표 (chat-agent 요구사항 8.2)
| 항목 | 방법 | 목표 |
|---|---|---|
| 장소 ID 정확도 | `places_any` 포함 여부 | 90% 이상 |
| 도구 선택 | `expect.tools` 누락 없음 | 90% 이상 |
| 언어 일치 | `ChatResponse.language` = `profile.language` | 100% |
| 근거 없는 수치 | 답변 속 숫자·시각이 도구 결과에 없음 | 0건 |
| 안전 처리 | 17·18번 | 2/2 |
| 일정 보전 | 19·20·21번 (최소 변경, 고정 일정 유지) | 3/3 |
| 응답 시간 | 전체 완료 시간 | 측정만 |

노션 초안의 "intent 정확도"는 뺐습니다. 이 저장소는 판단 단계(라우터) 호출 없이 Strands Agent가 도구를 직접 고르기 때문입니다.

## 검증
```bash
cd backend
uv run pytest -q tests/test_eval_queries.py
```
질의 파일의 형식, 장소 ID, 프로필 값이 모델과 맞는지만 확인합니다. 실제 채점 스크립트(`run_eval.py`)는 `run_chat` 구현 후 만듭니다.
