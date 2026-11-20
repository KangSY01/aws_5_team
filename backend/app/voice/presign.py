"""Amazon Transcribe Streaming WebSocket presigned URL (SigV4 쿼리 서명). AWS 를 부르지 않고 서명만 한다.

규격 (https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html):
  wss://transcribestreaming.<region>.amazonaws.com:8443/stream-transcription-websocket
  ?language-code=..&media-encoding=pcm&sample-rate=16000 + X-Amz-* 서명 파라미터
- 서명 서비스 이름 transcribe, 서명 헤더는 host(포트 8443 포함), 페이로드는 빈 문자열.
- X-Amz-Expires 는 최대 300초. URL 은 그 안에 연결을 시작하는 데만 쓰고, 연결된 스트림은 계속 쓸 수 있다.
- 임시 자격 증명(Lambda 역할)의 세션 토큰은 X-Amz-Security-Token 으로 들어간다. 비밀 키는 URL 에 들어가지 않는다.

서명은 botocore 의 SigV4QueryAuth 가 한다. URL 은 로그에 쓰지 않는다 (세션 토큰이 들어 있다).
"""

from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials

SERVICE = "transcribe"
PORT = 8443
PATH = "/stream-transcription-websocket"
MAX_EXPIRES = 300  # Transcribe 가 받는 X-Amz-Expires 상한


def host(region: str) -> str:
    return f"transcribestreaming.{region}.amazonaws.com:{PORT}"


def websocket_url(*, credentials: ReadOnlyCredentials, region: str, language_code: str, sample_rate: int,
                  media_encoding: str = "pcm", expires: int = MAX_EXPIRES) -> str:
    """서명된 wss URL. expires 는 1~300 초."""
    if not 1 <= expires <= MAX_EXPIRES:
        raise ValueError(f"expires 는 1~{MAX_EXPIRES} 초여야 합니다.")
    request = AWSRequest(
        method="GET",
        url=f"https://{host(region)}{PATH}",  # 서명은 https 로 계산하고 scheme 만 wss 로 바꾼다 (포트 8443 은 host 에 남는다)
        params={"language-code": language_code, "media-encoding": media_encoding, "sample-rate": str(sample_rate)},
    )
    SigV4QueryAuth(credentials, SERVICE, region, expires=expires).add_auth(request)
    url = request.prepare().url
    return "wss://" + url.removeprefix("https://")
