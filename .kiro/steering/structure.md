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
    agent.py        에이전트  Strands Agent 구성
    prompts.py      에이전트  시스템 프롬프트
    tools/          에이전트·도구  lookup.py(조회), plan_edit.py(부분 수정)
    guardian/       Guardian  check.py(점검), repair.py(해결안). LLM 미사용
    data/           데이터    mock 데이터 원본 (places.json, 샘플 응답)
    storage/        데이터    DynamoDB 읽기·쓰기
    config.py       환경 변수 설정
  scripts/          로컬 실행 (local_invoke, local_server)
  tests/            pytest
  eval/             평가 질의와 결과
docs/
  api-contract.md   공용 ⚠️  API 계약
frontend/           프론트   React + Vite + MapLibre
.kiro/steering/team.md  공용 ⚠️  팀 규칙 원본
```

| 역할 | 맡는 곳 |
|---|---|
| 에이전트·도구 | `backend/app/agent.py`, `backend/app/prompts.py`, `backend/app/tools/` |
| Guardian | `backend/app/guardian/` |
| 데이터·저장 | `backend/app/data/`, `backend/app/storage/` |
| 프론트 | `frontend/` |
| 인프라·배포 | Lambda, S3 + CloudFront, DynamoDB 배포 구성 |

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
