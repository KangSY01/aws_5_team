import { eventName, findStopEvent } from "../lib/stopEvent.js";
// 일정 목록: 날짜 제목과 stops 순서 그대로의 <ol>
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { tripCursorY } from '../lib/tripCursor.js';
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

export default function PlanList({ plan, places, displayLanguage, selected, tripStopId, onSelect, lockedLabel, onEdit, editLabel, formatStopDate, onSaveStops, busy, saveError, renderStopChecks, onToggleLock, lockCopy, events, checkedIds, legs, renderLeg, doneBefore }) {
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

  function move(from, to) {
    if (busy) return false;
    const reordered = reorderStops(stops, from, to);
    return reordered !== stops && onSaveStops(reordered);
  }

  const { drag, handleProps, cancel } = useStopDrag(list, stops, onSaveStops && !busy ? move : undefined);

  // 여행 진행 커서: 왼쪽 세로선 맨 위에서 현재 시각 위치까지 내려오는 사각형 (doneBefore = 여행 기준 시각)
  const section = useRef(null);
  const [cursor, setCursor] = useState(null);
  useLayoutEffect(() => {
    if (doneBefore === undefined || !stops.length) {
      setCursor(null);
      return undefined;
    }
    function measure() {
      const root = section.current?.getBoundingClientRect();
      const numbers = [...(list.current?.children ?? [])].map((item) => item.querySelector('.stop-number')?.getBoundingClientRect());
      if (!root || numbers.length !== stops.length || numbers.some((rect) => !rect?.height)) {
        setCursor(null);
        return;
      }
      const points = numbers.map((rect) => rect.top + rect.height / 2 - root.top);
      const y = tripCursorY(stops, points, doneBefore);
      setCursor(y === null ? null : { x: numbers[0].left + numbers[0].width / 2 - root.left, top: points[0], y });
    }
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(list.current);
    return () => observer.disconnect();
  }, [stops, doneBefore, legs]);

  return (
    <section className="plan-list" ref={section} data-trip-cursor={cursor ? '' : undefined}>
      {cursor && <span className="trip-progress-line" aria-hidden="true" style={{ left: cursor.x, top: cursor.top, height: cursor.y - cursor.top }} />}
      {cursor && <span className="trip-cursor" aria-hidden="true" style={{ left: cursor.x, top: cursor.y }} />}
      {/* plan.date 는 변환 없이 그대로 표시한다 */}
      {!onSelect && typeof date === 'string' && date !== '' && (
        <h2 className="plan-list__date">{date}</h2>
      )}
      {/* 재정렬 없이 plan.stops 순서 그대로, 같은 place_id 여도 병합·생략하지 않는다 */}
      {overlaps.size > 0 && <p className="stop-overlap-summary" role="status">{copy.overlap}</p>}
      {onToggleLock && <p className="stop-lock-hint">{lockCopy.hint}</p>}
      {saveError && !editorStop && <p className="stop-overlap-summary" role="alert">{saveError}</p>}
      <ol className="plan-list__stops" ref={list} onKeyDown={cancel}>
        {stops.map((stop, index) => (
          <StopItem
            key={keys[index]}
            stop={stop}
            place={placesById.get(stop?.place_id)}
            eventName={eventName(findStopEvent(stop, events), language)}
            language={language}
            number={onSelect ? index + 1 : undefined}
            active={checkedIds ? checkedIds.includes(stop.stop_id) : selected === index}
            checked={checkedIds ? checkedIds.includes(stop.stop_id) : undefined}
            tripTarget={tripStopId != null && stop.stop_id === tripStopId}
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
            checks={renderStopChecks?.(stop)}
            done={doneBefore !== undefined && Date.parse(stop.end) <= doneBefore}
            leg={index < stops.length - 1 && stops[index + 1].place_id !== stop.place_id && legs?.[stop.stop_id]
              ? renderLeg?.(legs[stop.stop_id]) : undefined}
            lock={onToggleLock ? {
              label: (name) => lockCopy.label(name, stop.locked),
              disabled: busy,
              toggle: () => onToggleLock(stop),
            } : undefined}
          />
        ))}
      </ol>
      {editorStop && (
        <StopTimeEditor key={editorTarget} stops={stops} index={editorIndex} name={resolvePlaceName(editorStop, placesById, language).name}
          copy={copy} busy={busy} error={saveError} formatStopDate={formatStopDate}
          onClose={() => setEditorTarget(null)} onSave={onSaveStops} />
      )}
    </section>
  );
}
