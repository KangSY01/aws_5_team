// 여행 진행 커서의 세로 위치 (일정 목록 왼쪽 세로선 위). points: 각 일정 번호 중심 y (위→아래)
// - 머무는 중: 그 일정 번호 위치
// - 이동 중: 앞 일정 종료 ~ 다음 일정 시작 사이 시간 비율만큼 두 번호 사이
// - 첫 일정 전: 첫 번호, 마지막 일정 후: 마지막 번호
export function tripCursorY(stops, points, now) {
  if (!stops.length || points.length !== stops.length) return null;
  for (let index = 0; index < stops.length; index += 1) {
    const start = Date.parse(stops[index].start);
    const end = Date.parse(stops[index].end);
    if (now < start) {
      if (index === 0) return points[0];
      const previousEnd = Date.parse(stops[index - 1].end);
      const ratio = start > previousEnd ? Math.min(1, Math.max(0, (now - previousEnd) / (start - previousEnd))) : 1;
      return points[index - 1] + (points[index] - points[index - 1]) * ratio;
    }
    if (now < end) return points[index];
  }
  return points[points.length - 1];
}
