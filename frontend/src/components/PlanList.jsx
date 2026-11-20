// 일정 목록: 날짜 제목과 stops 순서 그대로의 <ol>
import StopItem from './StopItem.jsx';
import { buildPlacesById } from '../lib/resolvePlaceName.js';

// stop_id 를 key 로 쓰되 중복이면 등장 순번을 붙여(s1, s1#2, ...) 고유하게 만든다
function buildKeys(stops) {
  const seen = new Map(); // stop_id → 지금까지 등장 횟수
  const used = new Set();
  return stops.map((stop) => {
    const id = String(stop?.stop_id);
    let count = (seen.get(id) ?? 0) + 1;
    let key = count === 1 ? id : `${id}#${count}`;
    // 실제 stop_id 가 "s1#2" 처럼 생긴 경우와 충돌하면 순번을 올린다
    while (used.has(key)) {
      count += 1;
      key = `${id}#${count}`;
    }
    seen.set(id, count);
    used.add(key);
    return key;
  });
}

export default function PlanList({ plan, places, displayLanguage, selected, onSelect, lockedLabel, onEdit, editLabel, formatStopDate }) {
  const stops = Array.isArray(plan?.stops) ? plan.stops : [];
  const placesById = buildPlacesById(places);
  const language = displayLanguage ?? plan?.profile?.language;
  const keys = buildKeys(stops);
  const date = plan?.date;

  return (
    <section className="plan-list">
      {/* plan.date 는 변환 없이 그대로 표시한다 */}
      {!onSelect && typeof date === 'string' && date !== '' && (
        <h2 className="plan-list__date">{date}</h2>
      )}
      {/* 재정렬 없이 plan.stops 순서 그대로, 같은 place_id 여도 병합·생략하지 않는다 */}
      <ol className="plan-list__stops">
        {stops.map((stop, index) => (
          <StopItem
            key={keys[index]}
            stop={stop}
            place={placesById.get(stop?.place_id)}
            language={language}
            number={onSelect ? index + 1 : undefined}
            active={selected === index}
            onSelect={onSelect ? () => onSelect(index) : undefined}
            lockedLabel={lockedLabel}
            onEdit={onEdit && !stop.locked ? () => onEdit(index) : undefined}
            editLabel={editLabel}
            dayLabel={formatStopDate && stop.start.slice(0, 10) !== date ? formatStopDate(stop.start.slice(0, 10)) : undefined}
          />
        ))}
      </ol>
    </section>
  );
}
