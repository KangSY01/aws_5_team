"""앱 언어 ↔ Amazon Transcribe Streaming 언어 코드.

- 인식 언어 코드(language-code): Transcribe 에 보내는 값. 사용자가 말하는 언어.
- 결과 문장 언어(transcript_language): 인식된 문장이 어떤 언어·문자로 나오는지. /chat 의 profile.language,
  음성 번역의 원문 언어로 쓴다. 중국어는 zh-CN 이 간체, zh-TW 가 번체로 나온다.

지원 여부는 Transcribe 지원 언어 표(스트리밍)에서 확인했다 (2026-11-20):
https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html
"""

from dataclasses import dataclass

from app.models.plan import Language


@dataclass(frozen=True)
class VoiceLanguage:
    app_language: Language  # 프로필 언어 (요청의 language)
    transcribe_code: str  # Transcribe language-code
    transcript_language: Language  # 인식된 문장의 언어·문자 (표시·채팅·번역에 쓴다)


VOICE_LANGUAGES: dict[Language, VoiceLanguage] = {
    "en": VoiceLanguage("en", "en-US", "en"),
    "ja": VoiceLanguage("ja", "ja-JP", "ja"),
    "zh-Hans": VoiceLanguage("zh-Hans", "zh-CN", "zh-Hans"),  # 표준 중국어, 간체로 출력
    "zh-Hant": VoiceLanguage("zh-Hant", "zh-TW", "zh-Hant"),  # 표준 중국어(대만), 번체로 출력
}


def transcribe_code(language: Language) -> str:
    """앱 언어의 Transcribe 언어 코드. 모르는 언어는 KeyError (요청 모델이 먼저 막는다)."""
    return VOICE_LANGUAGES[language].transcribe_code


def transcript_language(code: str) -> Language:
    """Transcribe 언어 코드로 인식된 문장의 앱 언어. 음성 번역의 원문 언어를 정할 때 쓴다."""
    for voice in VOICE_LANGUAGES.values():
        if voice.transcribe_code == code:
            return voice.transcript_language
    raise KeyError(code)
