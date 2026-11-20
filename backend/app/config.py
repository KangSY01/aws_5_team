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

# DynamoDB 단일 테이블 이름 (USE_MOCK=1이면 필요 없음). 일정·세션이 같은 테이블에 pk/sk 로 저장된다
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "")

# 선택 항목 (없어도 missing_keys()에 걸리지 않는다)
KMA_API_KEY = os.environ.get("KMA_API_KEY", "")
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "")
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")


def missing_keys() -> list[str]:
    """현재 모드에서 필요한데 비어 있는 환경 변수 이름 목록. 비어 있으면 정상.

    AWS 자격 증명은 boto3 기본 체인(프로필·Lambda 역할)에 맡기므로 여기서 보지 않는다.
    """
    required = [] if USE_MOCK else ["DATA_GO_KR_KEY_DECODING", "DYNAMODB_TABLE"]
    return [name for name in required if not os.environ.get(name)]
