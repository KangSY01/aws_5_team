---
inclusion: always
---

# 프로젝트: 부산 외국인 관광객 다국어 맞춤형 안내 에이전트

## 한 줄 요약
영어·일본어·중국어(간체/번체) 관광객에게 프로필 맞춤 일정을 지도 위에 짜 주고,
혼잡·비·휴무·빠듯한 이동을 먼저 찾아 알린 뒤 일정을 최대한 지키면서 문제 구간만 고친다.
핵심 기능: Schedule Guardian.

## 스택
- 백엔드: Python 3.13, uv, Strands Agents SDK, boto3, Pydantic, pytest
- 프론트엔드: React (Vite, JavaScript), MapLibre GL JS
- 배포: AWS Lambda (Function URL → 이후 API Gateway), S3 + CloudFront, DynamoDB

## AWS 규칙
- 리전은 ap-northeast-2만 사용한다.
- Bedrock 모델 ID는 환경 변수 MODEL_ID. 기본값 global.anthropic.claude-haiku-5-5
- 키는 .env와 Lambda 환경 변수로만 다룬다. 코드·테스트·커밋에 키 값을 넣지 않는다.

## 역할 분리 (가장 중요)
- LLM: 장소 고르기, 이유 설명, 다국어 문장 생성
- 코드: 방문 순서, 시간 계산, 수치, 장소 ID 검증, 일정 점검(Guardian)
- 장소명·수치·시간·영업 정보는 도구 결과에 있는 값만 쓴다. 없으면 모른다고 답한다.
- 일정 수정은 전체 재생성 대신 부분 수정 도구(replace/add/remove/move_stop)로 한다.
- locked=true인 일정은 어떤 경우에도 수정하지 않는다.

## Schedule Guardian
- guardian/ 는 LLM을 쓰지 않는 순수 파이썬이다.
- check_plan(plan, context) -> list[Issue]. Issue 종류: crowded, rain, closed, tight_transfer
- 해결 순서: 시간 이동 → 순서 변경 → 비슷한 장소로 교체 → 제외. 변경이 작은 것부터.
- 보전 지표: 바뀐 곳 수, 유지한 곳 수, 늘어난 이동 시간(분), 고정 일정 유지 여부

## 데이터 해석 규칙
- 집중률(tatsCnctrRatedList)은 관광지마다 자기 최고 시기=100인 상대값이다. 장소끼리 비교하지 않는다.
  - 어디가 붐비나 = 월 방문자 합계, 언제 붐비나 = 집중률
- 집중률에 없는 명소(감천문화마을 등)는 요일 규칙으로 대체한다 (평일 낮음, 토 가장 높음, 일 높음).
- 대형 행사일은 행사 가중 규칙을 별도로 적용한다.

## 개발 모드 스위치
- USE_MOCK=1: 외부 API 대신 backend/app/data/ 의 샘플·캐시 데이터를 쓴다.
- FAKE_LLM=1: Bedrock을 호출하지 않고 고정 응답을 반환한다.
- DEMO_NOW: 설정하면 현재 시각 대신 이 값을 쓴다 (시간 이동 데모).

## 코드 규칙
- 에이전트는 Strands만 쓴다. LangChain 등 다른 에이전트 프레임워크를 섞지 않는다.
- 도구 함수는 app/tools/ 아래. docstring에 언제 쓰는지, 입력, 출력을 자세히 쓴다.
- 도구 반복 상한 5회, max_tokens 설정, 외부 API 타임아웃 5초 재시도 1회.
- Lambda: 모델 객체는 핸들러 밖에서 1회 생성, Agent는 요청마다 생성. 스트리밍은 쓰지 않는다.
- 응답 형식은 docs/api-contract.md를 따른다.
- 주석과 로그는 한국어.

## 공용 파일과 mock 데이터
- 공용 파일은 뼈대 담당자 리뷰를 거친 PR로만 수정한다:
  backend/app/models/, docs/api-contract.md, backend/app/handler.py, .kiro/steering/team.md
- mock 데이터 원본은 backend/app/data/ 이다. 프론트엔드 mock은 그 복사본이다.

## 작업 방식
- 한 번에 한 단계만. 단계가 끝나면 실행·테스트 방법을 알려 주고 멈춘다.
- Strands·Bedrock API는 추측하지 말고 최신 공식 문서 기준으로 쓴다.
