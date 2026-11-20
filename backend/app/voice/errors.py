"""음성 입력 오류. handler.py 가 api-contract 오류 형식으로 바꾼다.

| 예외 | 상태 | code |
|---|---|---|
| VoiceServiceError | 500 | internal_error (사유는 로그에만 남기고 응답에 담지 않는다) |

언어가 지원 목록에 없는 요청은 VoiceUrlRequest 검증에서 422 validation_error 가 된다.
"""


class VoiceServiceError(Exception):
    """설정 누락, 자격 증명 없음, 서명 실패."""
