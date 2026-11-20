// 출처 표시와 비 예보 배너 (D). 화면 연결은 C 가 한다.
//
// ChatSources: /chat 답변 아래 "출처: 한국관광공사 · 기상청"
//   <ChatSources sources={chat.sources} language={language} />
//   - sources: /chat 응답의 sources 그대로 ([{ tool, id, title }]). 장소 추천 카드에 쓰는 흐름은 그대로 두고 같은 값을 넘긴다
//   - 보여 줄 기관이 없으면(sources 없음·빈 배열·일정 도구만) 아무것도 그리지 않는다
//
// RainNotice: 지도 상단 비 예보 배너 (데모 장면 5)
//   <RainNotice language={language} placeName={...선택} onOpen={...선택} disabled={...선택} />
//   - 데모 스위치가 켜져 있고 날씨가 rain-afternoon 일 때만 보인다 (데모 스위치를 직접 읽으므로 조건을 넘기지 않아도 된다)
export { default as ChatSources } from "./ChatSources.jsx";
export { default as RainNotice } from "./RainNotice.jsx";
export { providerNames } from "./copy.js";
