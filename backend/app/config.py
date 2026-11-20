"""환경 변수 기반 설정. 키 값은 .env / Lambda 환경 변수에만 두고 코드에는 넣지 않는다."""

import os


def _flag(name: str) -> bool:
    return os.environ.get(name, "0") == "1"


# 개발 모드 스위치
USE_MOCK = _flag("USE_MOCK")  # 외부 API 대신 app/data/ 샘플·캐시 사용
FAKE_LLM = _flag("FAKE_LLM")  # Bedrock 호출 없이 고정 응답
DEMO_NOW = os.environ.get("DEMO_NOW") or None  # ISO 시각 문자열. 있으면 현재 시각 대신 사용

# Bedrock
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-5-5")
BEDROCK_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
BEDROCK_EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "")  # 선택

# 공공데이터포털 키 (USE_MOCK=1이면 필요 없음)
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY_DECODING", "")  # Decoding 키 (requests가 URL 인코딩을 한다)
DATA_GO_KR_KEY_ENCODING = os.environ.get("DATA_GO_KR_KEY_ENCODING", "")  # 선택

# DynamoDB 단일 테이블 이름 (메모리 저장소면 필요 없음). 일정·세션이 같은 테이블에 pk/sk 로 저장된다
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "")
CACHE_TABLE = os.environ.get("CACHE_TABLE", "busan-guide-cache")  # 외부 API 응답 캐시 테이블 (get_weather). infra/base

# 사진 업로드 버킷 (공용 스택 busan-guide-base 출력 UploadsBucketName). USE_MOCK=1 이면 필요 없음.
# app/photo 가 presigned PUT URL 서명과 Textract 읽기에 쓴다
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")

# 저장소 종류: "memory" | "dynamodb" | "" (비우면 USE_MOCK 을 따른다: 1 이면 memory, 아니면 dynamodb)
# AWS 배포는 "dynamodb" 로 고정한다. 그래야 USE_MOCK=1(샘플 데이터)로 통제 테스트를 해도 일정이 DynamoDB 에 남는다
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "").strip().lower()
STORAGE_BACKENDS = ("memory", "dynamodb")


def use_memory_storage() -> bool:
    """메모리 저장소를 쓸지. 호출할 때의 USE_MOCK 값을 읽는다 (테스트가 값을 바꿀 수 있게)."""
    if STORAGE_BACKEND and STORAGE_BACKEND not in STORAGE_BACKENDS:
        raise ValueError(f"STORAGE_BACKEND 는 {', '.join(STORAGE_BACKENDS)} 중 하나여야 합니다 (현재: {STORAGE_BACKEND}).")
    return STORAGE_BACKEND == "memory" if STORAGE_BACKEND else USE_MOCK

# 선택 항목 (없어도 missing_keys()에 걸리지 않는다)
KMA_API_KEY = os.environ.get("KMA_API_KEY", "")
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "")
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")


def missing_keys() -> list[str]:
    """현재 모드에서 필요한데 비어 있는 환경 변수 이름 목록. 비어 있으면 정상.

    AWS 자격 증명은 boto3 기본 체인(프로필·Lambda 역할)에 맡기므로 여기서 보지 않는다.
    """
    required = [] if USE_MOCK else ["DATA_GO_KR_KEY_DECODING", "UPLOADS_BUCKET"]
    if not use_memory_storage():
        required.append("DYNAMODB_TABLE")
    return [name for name in required if not os.environ.get(name)]
