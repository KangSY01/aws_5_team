// 현지인에게 보여주기 카드 (D, 장면 4).
// - LocalCard: 한국어 문장 하나를 크게 보여 주고 🔊 로 /speak 한국어 음성을 재생한다 (채팅 답변의 "現地の人に見せる" 버튼에서 연다)
// - LocalCardPicker: 고정 문구 목록 → 카드 (여행 중 모드 버튼에서 연다)
export { default as LocalCard } from "./LocalCard.jsx";
export { default as LocalCardPicker } from "./LocalCardPicker.jsx";
export { PHRASES, findPhrase } from "./phrases.js";
export { fetchSpeech } from "./speakClient.js";
