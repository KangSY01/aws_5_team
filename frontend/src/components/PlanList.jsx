// 일정 목록: 날짜 제목과 stops 순서 그대로의 <ol>
import { useMemo, useRef, useState } from 'react';
import StopItem from './StopItem.jsx';
import StopTimeEditor from './StopTimeEditor.jsx';
import { buildPlacesById, resolvePlaceName } from '../lib/resolvePlaceName.js';
import { canMoveStop, overlappingStops, reorderStops, stopDate } from '../lib/itineraryTiming.js';
import { getItineraryEditCopy } from '../constants/itineraryEditCopy.js';
import { useStopDrag } from '../hooks/useStopDrag.js';

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

export default function PlanList({ plan, places, displayLanguage, selected, onSelect, lockedLabel, onEdit, editLabel, formatStopDate, onSaveStops, busy, saveError }) {
  const stops = Array.isArray(plan?.stops) ? plan.stops : [];
  const placesById = buildPlacesById(places);
  const language = displayLanguage ?? plan?.profile?.language;
  const keys = buildKeys(stops);
  const date = plan?.date;
  const copy = getItineraryEditCopy(language);
  const list = useRef(null);
  const [editorTarget, setEditorTarget] = useState(null);
  const editorIndex = editorTarget === null ? -1 : keys.indexOf(editorTarget);
  const editorStop = stops[editorIndex];
  const overlaps = useMemo(() => overlappingStops(stops), [stops]);

  function timeSave(start, end) {
    if (editorStop.start === start && editorStop.end === end) return true;
    return onSaveStops(stops.map((stop, index) => index === editorIndex ? { ...stop, start, end } : stop));
  }

  function move(from, to) {
    if (busy) return false;
    const reordered = reorderStops(stops, from, to);
    return reordered !== stops && onSaveStops(reordered);
  }

  function moveFromEditor(to) {
    if (!canMoveStop(stops, editorIndex, to)) return undefined;
    return async () => {
      if (await move(editorIndex, to)) setEditorTarget(null);
    };
  }

  const { drag, handleProps, cancel } = useStopDrag(list, stops, onSaveStops && !busy ? move : undefined);

  return (
    <section className="plan-list">
      {/* plan.date 는 변환 없이 그대로 표시한다 */}
      {!onSelect && typeof date === 'string' && date !== '' && (
        <h2 className="plan-list__date">{date}</h2>
      )}
      {/* 재정렬 없이 plan.stops 순서 그대로, 같은 place_id 여도 병합·생략하지 않는다 */}
      {overlaps.size > 0 && <p className="stop-overlap-summary" role="status">{copy.overlap}</p>}
      {saveError && !editorStop && <p className="stop-overlap-summary" role="alert">{saveError}</p>}
      <ol className="plan-list__stops" ref={list} onKeyDown={cancel}>
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
            day={formatStopDate && (index === 0 || stopDate(stop.start) !== stopDate(stops[index - 1].start))
              ? stopDate(stop.start) : undefined}
            formatStopDate={formatStopDate}
            timing={onSaveStops && !stop.locked ? {
              label: copy.edit,
              disabled: busy,
              open: () => setEditorTarget(keys[index]),
              handle: handleProps(index),
              hint: [index - 1, index + 1].some((to) => canMoveStop(stops, index, to)) ? copy.dragHint : undefined,
            } : undefined}
            overlap={overlaps.has(index) ? copy.overlap : undefined}
            dragging={drag?.from === index}
            insertion={drag?.to === index && drag.from !== index ? (drag.from > index ? 'before' : 'after') : undefined}
          />
        ))}
      </ol>
      {editorStop && (
        <StopTimeEditor key={editorTarget} stop={editorStop} name={resolvePlaceName(editorStop, placesById, language).name}
          copy={copy} busy={busy} error={saveError} formatStopDate={formatStopDate}
          onClose={() => setEditorTarget(null)} onSave={timeSave}
          onUp={moveFromEditor(editorIndex - 1)} onDown={moveFromEditor(editorIndex + 1)} />
      )}
    </section>
  );
}
