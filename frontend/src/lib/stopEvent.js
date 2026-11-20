// 일정 칸(Stop)이 그 장소에서 열리는 행사 시간과 겹치면 그 행사를 돌려준다.
// 같은 장소를 두 번 방문하는 일정(예: 해운대해수욕장 낮 방문과 저녁 해운대 빛축제)에서 두 번째 칸이 무엇인지 보여 주려고 쓴다.
// events 는 GET /events 결과(useMapEvents). 겹침 기준은 [stop.start, stop.end) 와 [event.start, event.end) 가 한 순간이라도 겹치는지다.
export function findStopEvent(stop, events) {
  if (!stop?.place_id || !Array.isArray(events)) return null;
  const start = Date.parse(stop.start);
  const end = Date.parse(stop.end);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return events.find((event) => {
    const places = Array.isArray(event?.place_ids) ? event.place_ids : [event?.main_place_id];
    if (!places.includes(stop.place_id)) return false;
    const eventStart = Date.parse(event.start);
    const eventEnd = Date.parse(event.end);
    return Number.isFinite(eventStart) && Number.isFinite(eventEnd) && eventStart < end && start < eventEnd;
  }) ?? null;
}

export function eventName(event, language) {
  return event?.names?.[language] ?? event?.names?.en ?? event?.name ?? "";
}
