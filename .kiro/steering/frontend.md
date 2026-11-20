---
inclusion: fileMatch
fileMatchPattern: ["frontend/**"]
---

# 프론트엔드 규칙

## 기술
- React + Vite + JavaScript. TypeScript를 도입하지 마십시오.
- API 요청·응답 형식은 `docs/api-contract.md`를 따릅니다. 필드 이름을 바꾸거나 추가하지 마십시오.
- mock 데이터는 `backend/app/data/`의 복사본으로 만듭니다. 원본이 바뀌면 복사본을 같이 맞춥니다.
- API 주소는 환경 변수(`VITE_API_BASE`)로 읽습니다. 로컬 백엔드는 `http://127.0.0.1:8000`입니다.

## API 사용 흐름
- 일정 표시: `GET /plan/{plan_id}`. 장소 이름은 `places[].names[profile.language]`로 표시합니다.
- 채팅: `POST /chat`. 첫 메시지는 `session_id`, `plan_id`를 `null`로 보내고 응답 값을 저장합니다.
- 채팅 응답의 `plan_changes`가 비어 있지 않으면 `GET /plan/{plan_id}`로 다시 읽고, 바뀐 카드를 강조합니다.
- 점검: 일정을 읽거나 바꾼 뒤 `POST /plan/check`를 호출해 배지를 갱신합니다.
- 해결안 적용: 선택한 `RepairOption.changes`를 일정에 반영해 `PUT /plan/{plan_id}`로 저장합니다.
- 되돌리기: 적용 직전 `Plan`을 화면 상태에 보관했다가 `PUT`으로 다시 저장합니다. 되돌리기 API는 없습니다.
- `/chat`은 `Accept: text/event-stream` 헤더로 요청해 SSE로 받습니다. `delta`의 `text`를 도착하는 대로 이어 붙여 표시하고, `done`의 `ChatResponse`로 마무리합니다. 형식은 `docs/api-contract.md` 「스트리밍」을 따릅니다.
- 브라우저 `EventSource`는 POST를 보낼 수 없으므로 `fetch` 응답 본문을 읽어 SSE를 직접 해석합니다.
- 나머지 경로의 응답은 한 번에 옵니다. 기다리는 동안 진행 표시를 보여 줍니다.

## 지도
- MapLibre GL JS + 오픈스트리트맵 벡터 타일을 쓰십시오. 카카오맵 바탕 지도는 쓰지 마십시오.
- 언어 전환 시 지명 필드를 `name:en`, `name:ja`, `name:zh-Hans`, `name:zh-Hant`로 바꾸고, 값이 없으면 `name`을 씁니다.
- 핀 좌표는 `Place.lat`, `Place.lng`입니다.

## 화면 구조
- 계획 모드: 지도 + 아래 시트, 책갈피 탭(Plan / Chat), 하단 고정 입력바
- 여행 중 모드: 다음 목적지 카드, 현지인에게 보여주기 카드, 늦었어요 / 붐벼요 / 도움 버튼
- 채팅으로 일정이 바뀌면 해당 카드 강조 + "변경됨 · 되돌리기" 알림을 표시합니다.

## Schedule Guardian 표시
- 배지는 `Issue.severity`로 정합니다: `high` 🔴(대안 권장), `medium` 🟡(주의), `low`는 배지 없이 목록에만 표시합니다.
- 한 화면에 배지는 최대 3개까지 표시합니다. `severity`가 높은 순, 같으면 해당 Stop 시작 시각이 이른 순으로 고릅니다.
- 배지를 누르면 대안 미리보기 시트를 엽니다.
  - 구성: 이유 한 줄 · `repairs[issue_id]`의 해결안 2~3개 · 해결안마다 보전 지표("변경 1곳 · 3곳 유지 · 이동 +5분 · 고정 일정 유지") · [바꾸기] / [그대로 갈래요]
  - 교체 후보 장소 정보는 `/plan/check` 응답의 `places`에서 찾습니다.
- [그대로 갈래요]는 화면 상태에서 해당 `issue_id`를 숨깁니다. 닫기 API는 없습니다.
- 일정 카드마다 🔒 고정 버튼을 두고, 누르면 `locked`를 바꿔 `PUT /plan/{plan_id}`로 저장합니다.
- 혼잡도 옆에 "장소별 평소 대비 값" 문구를 함께 표시합니다(다른 장소와 비교 불가).

## 문구와 번역
- UI 고정 문구는 `frontend/src/i18n/{en,ja,zh-Hans,zh-Hant}.json`에 둡니다.
- `Issue.detail`은 개발자용 한국어 문장입니다. 화면에는 `Issue.type`과 `severity`로 번역 사전 문구를 만들어 표시합니다.
- 열차 시각은 "시간표 기준" 표기를 함께 표시합니다.

## 데모 스위치
- `/chat`, `/plan/check`, `/plan/{plan_id}/delay` 요청에 `demo`(`now`, `weather_preset`)를 넣어 그 요청에서만 시각과 날씨를 바꿉니다. 형식은 `docs/api-contract.md` 「데모 스위치」입니다.
- 데모 스위치 패널(`frontend/src/features/demo-panel/`)은 D가 맡습니다.

## 접근성과 성능
- 터치 영역 44px 이상
- `prefers-reduced-motion` 설정 시 애니메이션 끔
- 무거운 3D·영상 대신 CSS 애니메이션(이동·회전·투명도)과 벡터 지도 사용
- 일본어·중국어 본문은 차분한 패널에 표시합니다. 지도와 전환 효과는 화려하게, 글 영역은 가독성을 우선합니다.
