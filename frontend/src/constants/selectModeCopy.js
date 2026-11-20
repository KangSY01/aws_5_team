// 일정 선택 모드 문구 (여러 장소 선택 → 삭제 또는 AI 채팅 멘션)
const copies = {
  ko: { toggle: "장소 선택", done: "선택 끝내기", count: (n) => `${n}곳 선택`, none: "장소를 눌러 선택하세요", remove: "삭제", mention: "AI에게 물어보기", lockedKept: "고정된 장소는 삭제하지 않아요", removeMention: (name) => `${name} 멘션 빼기`, mentionLabel: "멘션한 장소" },
  en: { toggle: "Select stops", done: "Done selecting", count: (n) => `${n} selected`, none: "Tap stops to select", remove: "Delete", mention: "Ask AI", lockedKept: "Locked stops are not deleted", removeMention: (name) => `Remove ${name}`, mentionLabel: "Mentioned stops" },
  ja: { toggle: "場所を選択", done: "選択を終える", count: (n) => `${n}件選択`, none: "場所をタップして選択", remove: "削除", mention: "AIに聞く", lockedKept: "固定した予定は削除しません", removeMention: (name) => `${name}を外す`, mentionLabel: "メンションした場所" },
  "zh-Hans": { toggle: "选择地点", done: "完成选择", count: (n) => `已选 ${n} 处`, none: "点按地点进行选择", remove: "删除", mention: "问 AI", lockedKept: "已固定的行程不会删除", removeMention: (name) => `移除 ${name}`, mentionLabel: "已提及的地点" },
  "zh-Hant": { toggle: "選擇地點", done: "完成選擇", count: (n) => `已選 ${n} 處`, none: "點按地點進行選擇", remove: "刪除", mention: "問 AI", lockedKept: "已固定的行程不會刪除", removeMention: (name) => `移除 ${name}`, mentionLabel: "已提及的地點" },
};

export function getSelectModeCopy(language) {
  return copies[language] ?? copies.en;
}
