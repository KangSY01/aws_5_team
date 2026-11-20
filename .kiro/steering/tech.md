---
inclusion: fileMatch
fileMatchPattern: ["backend/**", "frontend/package.json"]
---

# 기술 규칙

스택과 AWS 규칙의 원본은 `.kiro/steering/team.md`입니다. 이 문서는 그 규칙을 실제로 적용하는 방법만 적습니다. 두 문서가 다르면 `team.md`를 따르십시오.

## 백엔드 실행
- 모든 명령은 `backend/`에서 uv로 실행합니다.
  ```bash
  uv sync
  uv run pytest -q
  uv run python -m scripts.local_invoke   # handler 직접 호출
  uv run python -m scripts.local_server   # http://127.0.0.1:8000
  uv run --env-file .env <명령>           # .env 값을 넣어 실행
  ```
- 스크립트는 `python -m scripts.이름` 형식으로 실행합니다. `python scripts/이름.py`로 실행하면 `app`을 찾지 못합니다.
- 의존성은 `uv add <패키지>`(개발용은 `uv add --dev`)로 추가해 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.

## 배포 구성
- 배포는 SAM + AgentCore를 먼저 시도합니다. 금 12:00 점검 1까지 AgentCore가 안 되면 지금 뼈대 구조로 전환합니다: Lambda 하나(`app.handler.handler`)가 모든 경로를 처리하고, Function URL로 시작해 이후 API Gateway HTTP API(payload v2.0)로 옮깁니다. 경로별 배치는 배포 담당(A)이 정합니다.
- 배포 도구는 SAM입니다. 템플릿과 배포 설정은 `infra/`(A)에 둡니다.
- CORS 헤더는 핸들러가 붙이지 않습니다. 배포에서는 Function URL 설정, 로컬에서는 `scripts/local_server.py`가 담당합니다.
- 프론트엔드: S3 + CloudFront. 저장소: DynamoDB.
- FastAPI, Django, Firebase, LangChain은 쓰지 않습니다.

## 응답 스트리밍
- `/chat`만 스트리밍합니다. 나머지 경로는 한 번에 돌려줍니다.
- SSE 이벤트 형식(`delta`, `done`, `error`)은 `docs/api-contract.md` 「스트리밍」을 따릅니다. 배포 방식은 금 12:00 점검 1에서 배포 구성에 맞춰 확인합니다. 이벤트 형식은 어느 쪽이든 같습니다.
  - AgentCore Runtime은 SSE 스트리밍을 지원합니다. ([AgentCore 응답 스트리밍](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/response-streaming.html))
  - Lambda 관리형 런타임에서 응답 스트리밍을 기본 지원하는 것은 Node.js뿐입니다. Python Lambda는 사용자 지정 런타임이나 Lambda Web Adapter가 필요합니다. ([Lambda 응답 스트리밍](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html))

## Bedrock
- 모델 ID는 `config.MODEL_ID`(환경 변수 `BEDROCK_MODEL_ID`), 리전은 `config.BEDROCK_REGION`(환경 변수 `AWS_REGION`, 기본 `ap-northeast-2`)으로 읽습니다. 코드에 직접 쓰지 마십시오.
- `global.` 접두사는 교차 리전 추론 프로필입니다. 대회 계정에서 실제로 호출되는 ID를 확인해 `.env`에 둡니다.
- IAM 권한은 `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`입니다. Converse API도 이 권한을 씁니다.
- 모델 객체는 모듈 로드 때 1회 만들고, Agent는 요청마다 만듭니다. `max_tokens`를 설정하고 도구 반복은 5회까지입니다.
- Strands·Bedrock 사용법은 MCP 서버(`strands`, `aws-docs`)로 공식 문서를 확인한 뒤 씁니다.

## 설정과 비밀 값
- 설정은 `backend/app/config.py`의 모듈 상수로 읽습니다. `os.environ`을 다른 파일에서 직접 읽지 마십시오.
- 새 환경 변수가 필요하면 `config.py`와 `backend/.env.example`에 함께 추가하고, 필수 키면 `missing_keys()`에도 넣습니다.
- 키 값은 `backend/.env`와 Lambda 환경 변수에만 둡니다. 코드·테스트·로그·커밋에 넣지 마십시오.
- 공공데이터포털 키는 `DATA_GO_KR_KEY_DECODING`에 Decoding 키 값을 넣고(Encoding 키는 선택 항목 `DATA_GO_KR_KEY_ENCODING`), HTTP 라이브러리의 쿼리 파라미터로 넘깁니다. 인코딩은 라이브러리에 맡깁니다.

## 개발 모드 스위치
| 변수 | 뜻 |
|---|---|
| `USE_MOCK=1` | 외부 API 대신 `backend/app/data/`의 샘플·캐시를 씁니다 |
| `FAKE_LLM=1` | Bedrock을 호출하지 않고 고정 응답을 돌려줍니다 |
| `DEMO_NOW` | 값이 있으면 현재 시각 대신 이 ISO 시각을 씁니다 (시간 이동 데모) |

- 현재 시각이 필요한 코드는 `datetime.now()`를 직접 부르지 말고 `config.DEMO_NOW`를 먼저 확인하는 공용 함수 하나를 거칩니다.
- 새 기능은 `USE_MOCK=1`, `FAKE_LLM=1`에서도 동작해야 합니다. 테스트는 이 모드로 돌립니다.

## 코드 스타일
- Python 3.13, 타입 힌트, Pydantic 모델, pytest. 짧은 함수로 나눕니다.
- 외부 API는 타임아웃 5초, 재시도 1회입니다.
- 프론트엔드는 React + Vite + JavaScript입니다. TypeScript로 바꾸지 마십시오.
- 주석·로그·문서는 한국어, 식별자는 영어로 씁니다.
- 모델이 읽는 문장(시스템 프롬프트, `@tool` docstring과 `Args:`)은 영어로 씁니다. Strands `@tool`은 docstring을 도구 설명으로 모델에 보냅니다. 기존 도구의 한국어 docstring은 그 도구를 구현할 때 함께 바꿉니다.

## 계획 중인 AWS 기능
음성 입력(Transcribe)·여행 중 음성 출력(Polly)은 `product.md`의 3순위, 메뉴판·간판 사진 인식(Textract)·현지인 카드 한국어 음성(Polly)은 5순위 기능입니다. 모두 필수입니다. 경로와 형식은 `docs/api-contract.md` 「v0.2 추가 경로」(`/voice/url`, `/speak`, `/photo/upload-url`, `/photo/translate`)에 있습니다. 구현할 때 `handler.py` 연결 PR을 따로 올립니다.
