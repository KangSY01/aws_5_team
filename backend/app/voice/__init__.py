"""음성 입력 (A). 브라우저가 Amazon Transcribe Streaming(WebSocket)에 직접 연결할 presigned URL 을 발급한다.

서버는 오디오를 받지 않는다. 흐름:
  브라우저 마이크 → POST /voice/url (이 패키지) → wss presigned URL → 브라우저 ↔ Transcribe 직접 스트리밍
  → 인식된 문장 → (채팅) POST /chat 의 message / (나중에) 음성 번역

모듈:
- languages.py: 앱 언어(en, ja, zh-Hans, zh-Hant) ↔ Transcribe 언어 코드. 인식 결과 문장의 언어도 여기서 정한다.
  채팅과 음성 번역이 같이 쓴다.
- presign.py: SigV4 쿼리 서명으로 WebSocket URL 을 만든다 (AWS 호출 없음, 서명만).
- service.py: POST /voice/url 진입점. handler.py 가 부른다.
- errors.py: 설정·자격 증명 오류.

음성 번역으로 넓힐 때: 인식된 문장과 languages.transcript_language() 의 언어를 번역 모듈(Bedrock)에 넘긴다.
이 패키지는 음성 → 문장까지만 맡고, 번역·채팅 처리는 하지 않는다.
"""
