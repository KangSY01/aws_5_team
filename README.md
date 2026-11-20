# 부산 외국인 관광객 다국어 맞춤형 안내 에이전트

영어·일본어·중국어 관광객에게 맞춤 일정을 지도 위에 짜 주고, 혼잡·비·휴무·빠듯한 이동을 먼저 찾아 문제 구간만 고쳐 주는 에이전트입니다.

백엔드는 Lambda 핸들러(`backend/app/handler.py`)가 에이전트(Bedrock), Schedule Guardian, 조회 도구, 저장소를 실제로 호출합니다. 프론트엔드는 `frontend/`(React, Vite, MapLibre)입니다.
`USE_MOCK=1`이면 외부 API 대신 `backend/app/data/` 샘플을 쓰고, 일정은 메모리 저장소에 저장합니다.

- 대회: AWS AI 마에스트로 해커톤 (부산시 지역 현안)
- 제출 마감: 토 08:00 (목표 토 07:00)

## 설치와 실행

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.13은 uv가 알아서 받습니다.

```bash
cd backend
uv sync
uv run pytest -q                        # 테스트
uv run python -m scripts.local_invoke   # handler를 직접 호출해 샘플 요청 응답 출력
uv run python -m scripts.local_server   # 로컬 서버 http://127.0.0.1:8000 (CORS 허용)
```

스크립트는 반드시 `python -m scripts.이름` 형식으로 `backend/`에서 실행합니다. `python scripts/이름.py`로 실행하면 `app`을 찾지 못합니다.

## 담당 영역

역할 분담 원본은 노션 「역할 분담과 타임테이블」입니다.

| 역할 | 담당 | 맡는 곳 |
|---|---|---|
| A. 에이전트 백엔드 | 노윤지 | `backend/app/agent.py`, `backend/app/tools/plan_edit.py`, `backend/app/storage/`, `backend/app/voice/`(음성 입력 서명 URL), `backend/app/config.py`, `backend/scripts/`(B의 데이터 스크립트 제외), `infra/`(SAM 템플릿·배포 구성) |
| B. 데이터·도구 | 강서영 | `backend/app/data/`, `backend/app/tools/lookup.py`, `backend/app/tools/schedule.py`(일정 시각 계산), `backend/app/tools/return_options.py`(귀가 분산), `backend/app/tools/kakao_route.py`(카카오 대중교통 경로), `backend/app/tools/transit.py`(대중교통 추정), `backend/app/tools/restaurants.py`(음식점), `backend/app/tools/events_map.py`(지도용 행사), `backend/app/speech/`(음성 출력 Polly), `backend/scripts/`의 데이터 수집·생성 스크립트(`fetch_*`, `build_*`, `backfill_names`, `extract_station_names`, `demo_lookup`, `demo_offline_check`)와 시드·CSV |
| C. 프론트엔드 | 이지혜 | `frontend/` (D 폴더 제외) |
| D. 아키텍처 설계 인프라 | 이온규 | `backend/app/guardian/`(예약 점검 로직 `scheduled.py` 포함), `backend/app/prompts.py`, `backend/app/photo/`(사진 인식 백엔드), `backend/eval/`, `frontend/src/features/local-card/`, `frontend/src/features/demo-panel/`, `frontend/src/features/data-notices/`(출처 표시·비 예보 배너) |

담당 규칙 세부(테스트 파일, 예약 점검 연결, 계약에 없는 경로)는 [CONTRIBUTING.md](CONTRIBUTING.md)의 「담당 영역」을 따릅니다.

- `backend/app/handler.py`는 공용 파일입니다. 각 담당 모듈(`agent`, `guardian`, `tools`, `storage`, `photo`, `speech`)을 경로별로 호출하며, 수정은 아래 「공용 파일」 규칙을 따릅니다.

## 작업 규칙

- **협업 규칙 원본**: 브랜치·커밋·PR·머지 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다.
- **브랜치**: `feat/역할명`에서 작업하고 PR로 `main`에 합칩니다. `main`에 직접 push하지 않습니다.
- **공용 파일**: 아래 파일은 뼈대 담당자 리뷰를 받은 PR로만 수정합니다.
  - `backend/app/models/`
  - `docs/api-contract.md`
  - `backend/app/handler.py`
  - `.kiro/steering/team.md`
- **API 형식**: 요청·응답은 [docs/api-contract.md](docs/api-contract.md)를 따릅니다.
- **키**: `.env`는 커밋하지 않습니다. `backend/.env.example`을 `backend/.env`로 복사해 값을 채우고, `uv run --env-file .env <명령>`으로 실행합니다.
- **Kiro Spec**: 기능은 Kiro Spec으로 만듭니다. Kiro 사용도가 평가에 포함됩니다.
  - 팀 규칙 원본은 `.kiro/steering/team.md`이고 Kiro가 항상 읽습니다.
  - `.kiro/steering/`의 나머지 문서는 제품 개요, 기술 규칙, 구조, 데이터 규칙, API 계약 참조, 프론트엔드 규칙입니다. `team.md`와 다르면 `team.md`를 따릅니다.
  - 기능 스펙은 `.kiro/specs/`(`schedule-guardian`, `chat-agent`, `info-tools`, `return-dispersal`, `name-backfill`, `frontend-plan-list-skeleton`)에 있습니다. `tasks.md`의 작업을 순서대로 실행합니다.
  - MCP 서버(AWS 문서, Strands 문서)는 `.kiro/settings/mcp.json`에 설정돼 있습니다.
  - 크레딧 절약: 평소 작업은 Auto 또는 Sonnet, 막히는 문제만 Opus를 씁니다.

## 샘플 데이터

- mock 데이터 원본은 `backend/app/data/`입니다. 프론트엔드 mock은 그 복사본으로 만듭니다.
- `places.json`은 한국관광공사 다국어 관광정보로 수집한 값입니다(37곳, 해운대 로데오거리·부산 영화의 거리 포함).
- 저장소는 `STORAGE_BACKEND`(`memory` / `dynamodb`)로 정하고, 비어 있으면 `USE_MOCK=1`일 때 메모리, 아니면 DynamoDB입니다. `PUT /plan`은 선택한 저장소에 저장합니다.
- 메모리 저장소는 시작할 때 `sample_plan.json`의 `plan-1`을 저장합니다. 배포 환경(DynamoDB)에는 `plan-1`이 없으므로, `/chat`이 반환한 `plan_id`를 씁니다.

## 일정

원본은 노션 「역할 분담과 타임테이블」입니다.

| 시각 | 목표 |
|---|---|
| 목 23:00 | 점검 0: 뼈대 배포 (화면 → API → Bedrock "Hello", 못 끝내면 금 12:00까지) |
| 금 12:00 | 점검 1: 각자 모듈 단독 동작 시연 |
| 금 18:00 | 점검 2: 전체 연결 (1~2순위, 데모 장면 1·2) |
| 금 21:00 | 점검 3: 3·4·5순위 백엔드 동작 확인 |
| 토 00:00 | 기능 동결 (1~5순위 전부 화면에서 동작) |
| 토 01:30 | 리허설 1 |
| 토 03:00 | 코드 동결, `demo-v1` 태그 |
| 토 06:30 | 리허설 2 |
| 토 07:00 | 제출 |

## 데이터 출처

공공데이터를 기본으로 씁니다(한국관광공사 TourAPI·관광지 집중률, 기상청 단기예보, 부산교통공사 역 정보·열차시각표, 국가철도공단 역명). 공공데이터가 아닌 것은 실시간으로만 호출하는 카카오 API(대중교통 경로, 로컬 키워드 검색)이고, 결과를 저장·캐시하지 않습니다. 크롤링·리뷰 수집은 하지 않습니다.
출처별 파일, 기준일, 추정값 규칙은 [docs/data-sources.md](docs/data-sources.md)에 있습니다.

- **귀가 경로(데모 장면 7, `get_return_options`)**: 역 사이 시간은 카카오맵 대중교통 경로를 실시간으로 조회합니다. 조회가 실패하거나 `USE_MOCK=1`이거나 키가 없으면 역 좌표로 계산한 추정값을 씁니다. 항목마다 `time_source`(`kakao` / `estimate`)로 구분하고, 제안은 `rank_routes`로 정렬해 `ranked`에 담습니다.
- **막차**: 부산교통공사 열차시각표 조회 서비스(_GW)로 수집한 시각을 `last_trains.json`에 둡니다(해운대·동백·중동 → 서면, 서면 → 해운대). 귀가 경로의 모든 안에 `last_train`과 막차 경고(`last_train_missed` / `last_train_unknown`)가 붙습니다.
- **역명**: `stations.json`(1~4호선 108곳)의 2호선 역에 일본어·중국어(간체·번체) 역명이 있습니다(일본어 40곳, 간체·번체 39곳). 국가철도공단 부산 2호선 역명 데이터에 있는 값만 넣습니다.
- **비 대안**: `curation.json`의 비 올 때 대안 후보에서 대형 상업·유료 시설 3곳(씨라이프부산아쿠아리움, 부산엑스더스카이, 신세계백화점 센텀시티점)을 뺍니다.

지도: © OpenStreetMap contributors

## 제출용 섹션 (토 03:00 이후 작성)

- [ ] 문제 정의와 예상 고객
- [ ] 시스템 구조도 이미지
- [ ] 데모 영상 또는 스크린샷
- [ ] 평가 결과 (장소 ID 정확도, 근거 없는 수치 건수, 응답 시간)
- [ ] 팀원과 역할
- [ ] 확장 계획 (리뷰 광고 필터, 실시간 혼잡 데이터)
