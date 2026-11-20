// 현지인에게 보여주기 카드 고정 문구 (D, 장면 4). 화면에서 번역하지 않고 여기 문장만 쓴다.
// ko 는 카드에 크게 보이고 /speak 로 읽는 한국어, 나머지는 사용자가 뜻을 확인하는 번역이다.
// 문구를 고치면 일본어·중국어 확인을 다시 받는다 (노션 대본 「데모 사고 대비」 일본어 검수).

export const PHRASES = [
  {
    id: "less_spicy", // 장면 4 대본 문장
    ko: "덜 맵게 해 주실 수 있나요?",
    en: "Could you make it less spicy?",
    ja: "辛さを控えめにしてもらえますか？",
    "zh-Hans": "可以做得不那么辣吗？",
    "zh-Hant": "可以做得不那麼辣嗎？",
  },
  {
    id: "no_spicy",
    ko: "매운 음식을 못 먹어요.",
    en: "I can't eat spicy food.",
    ja: "辛い料理が食べられません。",
    "zh-Hans": "我不能吃辣的食物。",
    "zh-Hant": "我不能吃辣的食物。",
  },
  {
    id: "recommend",
    ko: "추천 메뉴가 뭐예요?",
    en: "What do you recommend?",
    ja: "おすすめのメニューは何ですか？",
    "zh-Hans": "有什么推荐的菜吗？",
    "zh-Hant": "有什麼推薦的菜嗎？",
  },
  {
    id: "pay_card",
    ko: "카드로 계산할 수 있나요?",
    en: "Can I pay by card?",
    ja: "カードで支払えますか？",
    "zh-Hans": "可以刷卡吗？",
    "zh-Hant": "可以刷卡嗎？",
  },
  {
    id: "restroom",
    ko: "화장실이 어디에 있나요?",
    en: "Where is the restroom?",
    ja: "トイレはどこですか？",
    "zh-Hans": "洗手间在哪里？",
    "zh-Hant": "洗手間在哪裡？",
  },
  {
    id: "photo",
    ko: "사진 좀 찍어 주실 수 있나요?",
    en: "Could you take a photo of us?",
    ja: "写真を撮っていただけますか？",
    "zh-Hans": "可以帮我们拍张照吗？",
    "zh-Hant": "可以幫我們拍張照嗎？",
  },
  {
    id: "help",
    ko: "좀 도와주실 수 있나요?",
    en: "Could you help me, please?",
    ja: "少し手伝っていただけますか？",
    "zh-Hans": "可以帮我一下吗？",
    "zh-Hant": "可以幫我一下嗎？",
  },
];

export const LANGUAGES = ["en", "ja", "zh-Hans", "zh-Hant"];

export function findPhrase(id) {
  return PHRASES.find((p) => p.id === id) ?? null;
}

// 카드 화면 고정 문구 (사용자 언어). 사용자가 보는 화면이라 4개 언어로 둔다.
export const COPY = {
  en: { title: "Show this to a local", listTitle: "Phrases to show", speak: "Play in Korean", speaking: "Playing…", loading: "Loading audio…", close: "Close", speakError: "Couldn't play the audio. Show the text instead.", meaning: "Meaning" },
  ja: { title: "現地の人に見せる", listTitle: "見せるフレーズ", speak: "韓国語で再生", speaking: "再生中…", loading: "音声を準備中…", close: "閉じる", speakError: "音声を再生できませんでした。画面の文字を見せてください。", meaning: "意味" },
  "zh-Hans": { title: "给当地人看", listTitle: "常用句子", speak: "用韩语播放", speaking: "正在播放…", loading: "正在准备语音…", close: "关闭", speakError: "无法播放语音，请直接出示文字。", meaning: "意思" },
  "zh-Hant": { title: "給當地人看", listTitle: "常用句子", speak: "用韓語播放", speaking: "正在播放…", loading: "正在準備語音…", close: "關閉", speakError: "無法播放語音，請直接出示文字。", meaning: "意思" },
};

export function copyFor(language) {
  return COPY[language] ?? COPY.en;
}
