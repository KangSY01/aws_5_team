// 여행 일시정지·재개, 여행 종료 평가 문구
const copies = {
  ko: {
    pause: "여행 일시정지", resume: "여행 다시 시작", paused: "일시정지",
    title: "오늘 루트 평가", visited: (n, total) => `${total}곳 중 ${n}곳 방문`,
    travel: (minutes) => `이동 ${minutes}분`, walk: (minutes) => `도보 ${minutes}분`, transit: (minutes) => `대중교통 ${minutes}분`,
    crowded: (n) => `혼잡 높은 장소 ${n}곳`, noCrowd: "혼잡 높은 장소 없음",
    rating: "루트 만족도", star: (n) => `${n}점`,
    tagsLabel: "어땠나요?", tags: ["이동이 편했어요", "혼잡을 잘 피했어요", "일정이 빡빡했어요", "다시 가고 싶어요"],
    save: "평가 저장하고 종료", skip: "평가 없이 종료", close: "닫기",
  },
  en: {
    pause: "Pause trip", resume: "Resume trip", paused: "Paused",
    title: "Rate today's route", visited: (n, total) => `${n} of ${total} stops visited`,
    travel: (minutes) => `${minutes} min of travel`, walk: (minutes) => `Walk ${minutes} min`, transit: (minutes) => `Transit ${minutes} min`,
    crowded: (n) => `${n} crowded stop${n === 1 ? "" : "s"}`, noCrowd: "No crowded stops",
    rating: "Route rating", star: (n) => `${n} star${n === 1 ? "" : "s"}`,
    tagsLabel: "How was it?", tags: ["Easy to get around", "Avoided the crowds", "Too packed", "Would go again"],
    save: "Save rating and end trip", skip: "End without rating", close: "Close",
  },
  ja: {
    pause: "旅行を一時停止", resume: "旅行を再開", paused: "一時停止中",
    title: "今日のルート評価", visited: (n, total) => `${total}か所中${n}か所訪問`,
    travel: (minutes) => `移動 ${minutes}分`, walk: (minutes) => `徒歩 ${minutes}分`, transit: (minutes) => `公共交通 ${minutes}分`,
    crowded: (n) => `混雑の高い場所 ${n}か所`, noCrowd: "混雑の高い場所なし",
    rating: "ルートの満足度", star: (n) => `${n}点`,
    tagsLabel: "いかがでしたか？", tags: ["移動が楽だった", "混雑を避けられた", "予定が詰まりすぎ", "また行きたい"],
    save: "評価を保存して終了", skip: "評価せずに終了", close: "閉じる",
  },
  "zh-Hans": {
    pause: "暂停行程", resume: "继续行程", paused: "已暂停",
    title: "今日路线评价", visited: (n, total) => `已游览 ${n}/${total} 处`,
    travel: (minutes) => `移动 ${minutes} 分钟`, walk: (minutes) => `步行 ${minutes} 分钟`, transit: (minutes) => `公共交通 ${minutes} 分钟`,
    crowded: (n) => `高拥挤地点 ${n} 处`, noCrowd: "没有高拥挤地点",
    rating: "路线满意度", star: (n) => `${n} 分`,
    tagsLabel: "感觉如何？", tags: ["出行方便", "避开了人潮", "行程太紧", "还想再去"],
    save: "保存评价并结束", skip: "不评价直接结束", close: "关闭",
  },
  "zh-Hant": {
    pause: "暫停行程", resume: "繼續行程", paused: "已暫停",
    title: "今日路線評價", visited: (n, total) => `已造訪 ${n}/${total} 處`,
    travel: (minutes) => `移動 ${minutes} 分鐘`, walk: (minutes) => `步行 ${minutes} 分鐘`, transit: (minutes) => `大眾運輸 ${minutes} 分鐘`,
    crowded: (n) => `高擁擠地點 ${n} 處`, noCrowd: "沒有高擁擠地點",
    rating: "路線滿意度", star: (n) => `${n} 分`,
    tagsLabel: "感覺如何？", tags: ["交通方便", "避開了人潮", "行程太緊", "還想再去"],
    save: "儲存評價並結束", skip: "不評價直接結束", close: "關閉",
  },
};

export function getTripReviewCopy(language) {
  return copies[language] ?? copies.en;
}
