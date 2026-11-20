"""POST /voice/url 진입점. handler.py 는 이 모듈의 함수만 부른다.

- 리전은 config.BEDROCK_REGION(AWS_REGION, ap-northeast-2). 서울 리전은 Transcribe Streaming 을 지원한다.
- 자격 증명은 boto3 기본 체인(Lambda 실행 역할)에서 읽는다. 코드·환경 변수에 키를 두지 않는다.
- USE_MOCK=1 이면 서명하지 않고 연결되지 않는 가짜 주소(.invalid)를 돌려준다 (로컬 개발, AWS 없음).
"""

import logging
from urllib.parse import urlencode

import boto3

from app import config
from app.models.api import VoiceUrlRequest, VoiceUrlResponse
from app.voice import languages, presign
from app.voice.errors import VoiceServiceError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # Hz. 16비트 PCM(리틀 엔디언) 모노. 브라우저가 이 값으로 바꿔 보낸다
MEDIA_ENCODING = "pcm"
EXPIRES_IN = presign.MAX_EXPIRES  # 300초 안에 연결을 시작해야 한다
MOCK_URL_BASE = "wss://mock-transcribe.invalid" + presign.PATH  # USE_MOCK=1. 실제로 연결되지 않는 주소


def _credentials():
    """Lambda 실행 역할(또는 로컬 프로필)의 자격 증명. 없으면 VoiceServiceError."""
    try:
        credentials = boto3.Session().get_credentials()
    except Exception as error:  # 프로필 설정 오류 등. 내용은 로그에만
        logger.error("음성 입력 URL 자격 증명을 읽지 못했습니다: %s", type(error).__name__)
        raise VoiceServiceError("자격 증명을 읽지 못했습니다.") from error
    if credentials is None:
        logger.error("음성 입력 URL 을 서명할 AWS 자격 증명이 없습니다.")
        raise VoiceServiceError("자격 증명이 없습니다.")
    return credentials.get_frozen_credentials()


def create_voice_url(request: VoiceUrlRequest) -> VoiceUrlResponse:
    """사용자가 말하는 언어로 Transcribe Streaming WebSocket URL 을 만든다."""
    code = languages.transcribe_code(request.language)
    if config.USE_MOCK:
        query = urlencode({"language-code": code, "media-encoding": MEDIA_ENCODING, "sample-rate": SAMPLE_RATE})
        return VoiceUrlResponse(url=f"{MOCK_URL_BASE}?{query}", expires_in=EXPIRES_IN, sample_rate=SAMPLE_RATE,
                                media_encoding=MEDIA_ENCODING)
    try:
        url = presign.websocket_url(credentials=_credentials(), region=config.BEDROCK_REGION, language_code=code,
                                    sample_rate=SAMPLE_RATE, media_encoding=MEDIA_ENCODING, expires=EXPIRES_IN)
    except VoiceServiceError:
        raise
    except Exception as error:  # 서명 실패. URL·토큰은 로그에 쓰지 않는다
        logger.error("음성 입력 URL 서명 실패: %s", type(error).__name__)
        raise VoiceServiceError("URL 을 만들지 못했습니다.") from error
    logger.info("음성 입력 URL 발급: language-code=%s", code)
    return VoiceUrlResponse(url=url, expires_in=EXPIRES_IN, sample_rate=SAMPLE_RATE, media_encoding=MEDIA_ENCODING)
