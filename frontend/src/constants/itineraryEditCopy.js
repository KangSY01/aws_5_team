const labels = {
  ko: ["방문 시간 편집", "시작 시간", "종료 시간", "저장", "취소", "종료 시간은 시작 시간보다 늦어야 합니다.", "다른 방문 시간과 겹칩니다", "방문 순서", "위로 이동", "아래로 이동", "번호를 길게 눌러 이동하거나 방문 시간 편집에서 이동 버튼을 사용하세요."],
  en: ["Edit visit time", "Start time", "End time", "Save", "Cancel", "End time must be after start time.", "Overlaps another visit", "Visit order", "Move up", "Move down", "Hold the number to drag, or use the move buttons in Edit visit time."],
  ja: ["訪問時間を編集", "開始時刻", "終了時刻", "保存", "キャンセル", "終了時刻は開始時刻より後にしてください。", "他の訪問時間と重複しています", "訪問順", "上へ移動", "下へ移動", "番号を長押しして移動するか、訪問時間の編集画面の移動ボタンを使ってください。"],
  "zh-Hans": ["编辑到访时间", "开始时间", "结束时间", "保存", "取消", "结束时间必须晚于开始时间。", "与其他到访时间重叠", "到访顺序", "上移", "下移", "长按编号拖动，或使用到访时间编辑窗口中的移动按钮。"],
  "zh-Hant": ["編輯到訪時間", "開始時間", "結束時間", "儲存", "取消", "結束時間必須晚於開始時間。", "與其他到訪時間重疊", "到訪順序", "上移", "下移", "長按編號拖曳，或使用到訪時間編輯視窗中的移動按鈕。"],
};

export function getItineraryEditCopy(language) {
  const [edit, start, end, save, cancel, invalidEnd, overlap, order, up, down, dragHint] = labels[language] ?? labels.en;
  return { edit, start, end, save, cancel, invalidEnd, overlap, order, up, down, dragHint };
}
