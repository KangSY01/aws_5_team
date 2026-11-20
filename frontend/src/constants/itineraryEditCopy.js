const labels = {
  ko: ["일정 편집", "시작 시간", "종료 시간", "저장", "취소", "종료 시간은 시작 시간보다 늦어야 합니다.", "다른 방문 시간과 겹칩니다", "방문 순서", "위로 이동", "아래로 이동", "번호를 길게 눌러 이동하거나 일정 편집에서 이동 버튼을 사용하세요.", "현재 {number}번째"],
  en: ["Edit itinerary stop", "Start time", "End time", "Save", "Cancel", "End time must be after start time.", "Overlaps another visit", "Visit order", "Move up", "Move down", "Hold the number to drag, or use the move buttons when editing the stop.", "Position {number}"],
  ja: ["予定を編集", "開始時刻", "終了時刻", "保存", "キャンセル", "終了時刻は開始時刻より後にしてください。", "他の訪問時間と重複しています", "訪問順", "上へ移動", "下へ移動", "番号を長押しして移動するか、予定の編集画面の移動ボタンを使ってください。", "現在 {number} 番目"],
  "zh-Hans": ["编辑行程", "开始时间", "结束时间", "保存", "取消", "结束时间必须晚于开始时间。", "与其他到访时间重叠", "到访顺序", "上移", "下移", "长按编号拖动，或使用行程编辑窗口中的移动按钮。", "当前第 {number} 站"],
  "zh-Hant": ["編輯行程", "開始時間", "結束時間", "儲存", "取消", "結束時間必須晚於開始時間。", "與其他到訪時間重疊", "到訪順序", "上移", "下移", "長按編號拖曳，或使用行程編輯視窗中的移動按鈕。", "目前第 {number} 站"],
};

export function getItineraryEditCopy(language) {
  const [edit, start, end, save, cancel, invalidEnd, overlap, order, up, down, dragHint, positionLabel] = labels[language] ?? labels.en;
  return { edit, start, end, save, cancel, invalidEnd, overlap, order, up, down, dragHint,
    position: (number) => positionLabel.replace("{number}", () => new Intl.NumberFormat(language).format(number)) };
}
