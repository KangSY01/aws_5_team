# 부산 외국인 관광객 다국어 맞춤형 안내 에이전트

영어·일본어·중국어 관광객에게 맞춤 일정을 지도 위에 짜 주고, 혼잡·비·휴무·빠듯한 이동을 먼저 찾아 문제 구간만 고쳐 주는 에이전트입니다.

이 저장소는 팀 공용 **뼈대**입니다. 모든 API 경로가 샘플 데이터로 고정 응답을 돌려주며, 기능 로직은 각 담당자가 채웁니다.

## 설치와 실행

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.13은 uv가 알아서 받습니다.

```bash
cd backend
uv sync
uv run pytest -q                        # 테스트
uv run python -m scripts.local_invoke   # handler를 직접 호출해 네 경로 응답 출력
uv run python -m scripts.local_server   # 로컬 서버 http://127.0.0.1:8000 (CORS 허용)
```

스크립트는 반드시 `python -m scripts.이름` 형식으로 `backend/`에서 실행합니다. `python scripts/이름.py`로 실행하면 `app`을 찾지 못합니다.

## 담당 영역

| 역할 | 맡는 곳 |
|---|---|
| 에이전트·도구 | `backend/app/agent.py`, `backend/app/prompts.py`, `backend/app/tools/` |
| Guardian | `backend/app/guardian/` |
| 데이터·저장 | `backend/app/data/`, `backend/app/storage/` |
| 프론트 | `frontend/` |
| 인프라·배포 | Lambda, S3 + CloudFront, DynamoDB 배포 구성 |

- 지금은 스텁입니다. `agent.py`, `guardian/`, `tools/`의 함수는 시그니처와 docstring, `TODO(담당)`만 있고 호출하면 `NotImplementedError`가 납니다.
- 구현한 뒤에는 `backend/app/handler.py`의 `TODO` 위치에서 고정 응답을 실제 호출로 바꿉니다. 이 파일은 공용 파일이라 아래 규칙을 따릅니다.
- 프론트엔드는 아직 없습니다. 담당자가 Kiro로 생성할 예정입니다.

## 작업 규칙

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
  - MCP 서버(AWS 문서, Strands 문서)는 `.kiro/settings/mcp.json`에 설정돼 있습니다.

## 샘플 데이터

- mock 데이터 원본은 `backend/app/data/`입니다. 프론트엔드 mock은 그 복사본으로 만듭니다.
- **`places.json`의 좌표, 다국어 이름, 가까운 역은 검증하지 않은 값입니다.** 공공데이터로 교체해야 합니다.
- 고정 응답이라 상태가 이어지지 않습니다. `plan-1` 외의 plan_id는 404이고, `PUT /plan`은 저장하지 않고 받은 일정을 그대로 돌려줍니다.
