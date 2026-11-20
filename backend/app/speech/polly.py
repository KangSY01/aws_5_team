"""문장을 음성(mp3)으로 바꾼다 (Amazon Polly). POST /speak 가 쓴다. 형식은 docs/api-contract.md 「POST /speak」.

- 리전은 config.BEDROCK_REGION(ap-northeast-2). 자격 증명은 boto3 기본 체인(프로필·Lambda 역할)에 맡긴다.
- USE_MOCK=1 이면 Polly 를 부르지 않고 app/data/speech/sample.mp3 (무음)를 돌려준다.
- 같은 (text, language) 는 메모리에 둔 결과를 다시 쓴다 (최대 CACHE_SIZE 개, Lambda 인스턴스가 살아 있는 동안).
- 실패하면 SpeechError 를 올린다. handler 가 api-contract 오류 형식으로 바꾼다.
- 로그에는 문장 원문을 남기지 않는다 (언어와 글자 수만).
"""

import functools
import logging
from pathlib import Path

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from app import config

logger = logging.getLogger(__name__)

SAMPLE_PATH = Path(__file__).parent.parent / "data" / "speech" / "sample.mp3"
CACHE_SIZE = 128
CONNECT_TIMEOUT_SEC = 3
READ_TIMEOUT_SEC = 10
RETRIES = 1  # botocore max_attempts 는 최초 호출을 뺀 재시도 횟수

# language → (VoiceId, Engine). `aws polly describe-voices --region ap-northeast-2` 로 확인한 값 (2026-11-20).
# 서울 리전에서 다섯 음성 모두 neural 엔진을 쓸 수 있다.
VOICES: dict[str, tuple[str, str]] = {
    "ko": ("Seoyeon", "neural"),  # ko-KR
    "en": ("Joanna", "neural"),  # en-US
    "ja": ("Kazuha", "neural"),  # ja-JP
    "zh-Hans": ("Zhiyu", "neural"),  # cmn-CN (표준 중국어)
    # 번체 전용(대만 cmn-TW) 음성은 없다. 번체 사용자 다수가 쓰는 표준 중국어 음성을 쓴다.
    # 광둥어 음성(Hiujin, yue-CN)도 있지만 대만 사용자는 알아듣지 못한다.
    "zh-Hant": ("Zhiyu", "neural"),
}

class SpeechError(Exception):
    """음성을 만들지 못했다 (Polly 오류, 시간 초과, 빈 응답, 자격 증명 문제)."""


@functools.cache
def _polly():
    """Polly 클라이언트. 처음 쓸 때 한 번 만들고 그 뒤로는 같은 것을 쓴다.

    모듈을 불러올 때 만들지 않는 이유: boto3 는 클라이언트를 만들 때 자격 증명을 찾는데, 그 단계가 실패하는 환경
    (aws login 프로필 + botocore[crt] 없음)에서는 handler 를 불러오는 것부터 실패한다. USE_MOCK=1 은 여기까지 오지 않는다.
    """
    return boto3.client(
        "polly",
        region_name=config.BEDROCK_REGION,
        config=BotocoreConfig(
            connect_timeout=CONNECT_TIMEOUT_SEC, read_timeout=READ_TIMEOUT_SEC, retries={"max_attempts": RETRIES}
        ),
    )


@functools.lru_cache(maxsize=CACHE_SIZE)
def _synthesize(text: str, language: str) -> bytes:
    """Polly 호출. 성공한 결과만 캐시에 남는다 (예외는 캐시되지 않는다)."""
    voice, engine = VOICES[language]
    try:
        response = _polly().synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice, Engine=engine)
        audio = response["AudioStream"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("Polly 호출 실패: %s (language=%s, 글자 수=%d)", code, language, len(text))
        raise SpeechError(code) from None  # 원래 예외에는 요청 내용이 붙을 수 있어 이어 붙이지 않는다
    except BotoCoreError as e:
        logger.warning("Polly 호출 실패: %s (language=%s, 글자 수=%d)", type(e).__name__, language, len(text))
        raise SpeechError(type(e).__name__) from None
    if not audio:
        logger.warning("Polly 가 빈 음성을 돌려줬습니다 (language=%s, 글자 수=%d)", language, len(text))
        raise SpeechError("empty_audio")
    logger.info("음성 합성: language=%s, 글자 수=%d, %d바이트", language, len(text), len(audio))
    return audio


def synthesize(text: str, language: str) -> bytes:
    """text 를 language 의 음성으로 읽은 mp3 바이트. language 는 VOICES 의 키(SpeakRequest 가 검증한 값).

    Raises:
        SpeechError: Polly 호출이 실패했거나 지원하지 않는 language.
    """
    if language not in VOICES:
        raise SpeechError(f"unsupported language: {language}")
    if config.USE_MOCK:
        return SAMPLE_PATH.read_bytes()
    return _synthesize(text, language)
