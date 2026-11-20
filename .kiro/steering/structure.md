---
inclusion: always
---

# 저장소 구조와 작업 규칙

## 폴더와 담당
```
backend/
  app/
    handler.py      공용 ⚠️  Lambda 진입점, 경로 분기
    models/         공용 ⚠️  Pydantic 데이터·요청·응답 모델
    agent.py        A  Strands Agent 구성
    prompts.py      D  시스템 프롬프트
    tools/          A·B  lookup.py(공공데이터 조회, B), schedule.py(일정 시각 계산 build_plan, B), plan_edit.py(부분 수정, A)
    guardian/       D  check.py(점검), repair.py(해결안), scheduled.py(예약 점검). LLM 미사용
    photo/          D  사진 인식 (S3 presigned URL → Textract → Bedrock 번역)
    voice/          A  음성 입력 (Transcribe 서명 URL)
    speech/         B  음성 출력 (Polly)
    data/           B  mock 데이터 원본 (places.json, 샘플 응답)
    storage/        A  세션 저장 (DynamoDB 읽기·쓰기)
    config.py       A  환경 변수 설정
  scripts/          A  로컬 실행 (local_invoke, local_server)
  tests/            각자  test_<영역>.py
  eval/             D  평가 질의와 결과
infra/              A  SAM 템플릿·배포 구성
docs/
  api-contract.md   공용 ⚠️  API 계약
frontend/           C  React + Vite + MapLibre (features/local-card/, features/demo-panel/, features/data-notices/는 D)
.kiro/steering/team.md  공용 ⚠️  팀 규칙 원본
```

역할 분담 원본은 노션 「역할 분담과 타임테이블」입니다.

| 역할 | 담당 | 맡는 곳 |
|---|---|---|
| A. 에이전트 백엔드 | 노윤지 | `backend/app/agent.py`, `backend/app/tools/plan_edit.py`, `backend/app/storage/`, `backend/app/voice/`(음성 입력 서명 URL), `backend/app/config.py`, `backend/scripts/`, `infra/`(SAM 템플릿·배포 구성) |
| B. 데이터·도구 | 강서영 | `backend/app/data/`, `backend/app/tools/lookup.py`, `backend/app/tools/schedule.py`(일정 시각 계산), `backend/app/speech/`(음성 출력 Polly) |
| C. 프론트엔드 | 이지혜 | `frontend/` (D 폴더 제외) |
| D. 아키텍처 설계 인프라 | 이온규 | `backend/app/guardian/`(예약 점검 로직 `scheduled.py` 포함), `backend/app/prompts.py`, `backend/app/photo/`(사진 인식 백엔드), `backend/eval/`, `frontend/src/features/local-card/`, `frontend/src/features/demo-panel/`, `frontend/src/features/data-notices/`(출처 표시·비 예보 배너) |

- 테스트는 각자 `backend/tests/test_<영역>.py` 파일에 씁니다.
- 예약 점검 로직은 `guardian/scheduled.py`(D), Lambda 연결과 EventBridge 스케줄은 `infra/`(A)입니다.
- 새 경로는 `docs/api-contract.md` 「v0.2 추가 경로」에 있습니다. 구현한 담당자가 `handler.py` 연결 PR을 따로 올립니다.

## AI 에이전트(Kiro) 작업 규칙
- 요청받은 폴더 밖의 파일을 수정하지 마십시오. 필요하면 수정안만 제시하십시오.
- 공용 파일(⚠️ 표시)은 사람이 명시적으로 요청했을 때만 수정하고, 수정 내용을 PR 설명에 요약하십시오.
  - `backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`
- `handler.py`의 `TODO` 위치를 실제 구현 호출로 바꾸는 일도 공용 파일 수정입니다. 구현은 자기 폴더에서 끝내고 `handler.py` 변경은 따로 PR로 올립니다.
- 장소 ID는 `backend/app/data/places.json`에 있는 값만 쓰십시오. 새 ID를 만들지 마십시오.
- mock 데이터 원본은 `backend/app/data/`입니다. 프론트엔드 mock은 그 복사본이며, 원본을 바꾸면 복사본도 같은 PR에서 맞춥니다.
- 새 의존성은 백엔드 `uv add`, 프론트엔드 `package.json`에 반영하십시오.

## Git 규칙
원본은 루트 `CONTRIBUTING.md`입니다. 핵심만 요약합니다.

- 브랜치: `feat/역할명`에서 작업하고 PR로 `main`에 합칩니다. `main`에 직접 push하지 않습니다.
- 커밋 메시지: `type(scope): 요약` (예: `feat(guardian): 강수 점검 규칙 추가`)
- PR 본문: `.github/pull_request_template.md` 항목 작성
- 커밋 금지: `.env`, 키 값, 카카오 경로 결과
