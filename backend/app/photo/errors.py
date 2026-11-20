"""사진 인식 오류. handler.py 가 api-contract 오류 형식으로 바꾼다.

| 예외 | 상태 | code |
|---|---|---|
| PhotoKeyInvalid | 422 | validation_error |
| PhotoNotFound | 404 | not_found |
| PhotoUnreadable | 422 | validation_error |
| PhotoServiceError | 500 | internal_error (사유는 로그에만 남기고 응답에 담지 않는다) |
"""


class PhotoError(Exception):
    """사진 인식 오류의 공통 부모."""


class PhotoKeyInvalid(PhotoError):
    """/photo/upload-url 이 발급한 형식(photos/<32자 hex>.jpg|png)이 아닌 key. 버킷의 다른 객체를 읽지 못하게 막는다."""


class PhotoNotFound(PhotoError):
    """올린 사진이 없다 (업로드 전이거나 1일 보관 기간이 지남)."""


class PhotoUnreadable(PhotoError):
    """Textract 가 읽을 수 없는 이미지 (형식 오류, 10MB 초과 등)."""


class PhotoServiceError(PhotoError):
    """설정 누락이나 AWS 호출 실패."""
