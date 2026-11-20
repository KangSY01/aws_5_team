import { useId, useLayoutEffect, useRef, useState } from "react";
import { formatTime } from "../lib/formatTime.js";
import { canMoveStop, overlappingStops, reorderStops, stopDate } from "../lib/itineraryTiming.js";

export default function StopTimeEditor({ stops, index, name, copy, busy, error, formatStopDate, onClose, onSave }) {
  const dialog = useRef(null);
  const id = useId();
  const endField = useRef(null);
  const [position, setPosition] = useState(index);
  const [startOverride, setStart] = useState(null);
  const [endOverride, setEnd] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const ordered = reorderStops(stops, index, position);
  const stop = ordered[position];
  const startDay = stopDate(stop.start);
  const endDay = stopDate(stop.end);
  const start = startOverride ?? formatTime(stop.start);
  const end = endOverride ?? formatTime(stop.end);
  const updatedStart = start === formatTime(stop.start) ? stop.start : startDay + "T" + start + ":00+09:00";
  const updatedEnd = end === formatTime(stop.end) ? stop.end : endDay + "T" + end + ":00+09:00";
  const valid = Boolean(start && end && Date.parse(updatedStart) < Date.parse(updatedEnd));
  const unchangedTimes = updatedStart === stop.start && updatedEnd === stop.end;
  const next = unchangedTimes ? ordered : ordered.map((item, row) =>
    row === position ? { ...item, start: updatedStart, end: updatedEnd } : item);
  const overlaps = valid && [...overlappingStops(next)].some((row) =>
    row === position || !stops.includes(next[row]));
  const invalidEnd = submitted && !valid;

  function canPreviewPosition(target) {
    return target === index || canMoveStop(stops, index, target);
  }

  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!valid) {
      setSubmitted(true);
      endField.current.focus();
      return;
    }
    if (next === stops || await onSave(next)) onClose();
  }

  return (
    <dialog className="stop-time-dialog stop-editor-dialog" ref={dialog} aria-labelledby={id}
      onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <h2 id={id}>{copy.edit}</h2>
      <p className="stop-editor-place">{name}</p>
      <form onSubmit={submit} aria-busy={busy}>
        <div className="stop-time-fields">
          <label>
            {copy.start}
            {startDay !== endDay && <small>{formatStopDate?.(startDay) ?? startDay}</small>}
            <input required type="time" value={start} disabled={busy} aria-describedby={overlaps ? id + "-overlap" : undefined}
              onChange={(event) => { setStart(event.target.value); setSubmitted(false); }} />
          </label>
          <label>
            {copy.end}
            {startDay !== endDay && <small>{formatStopDate?.(endDay) ?? endDay}</small>}
            <input required type="time" value={end} ref={endField} disabled={busy}
              aria-invalid={invalidEnd || undefined}
              aria-describedby={invalidEnd ? id + "-error" : overlaps ? id + "-overlap" : undefined}
              onChange={(event) => { setEnd(event.target.value); setSubmitted(false); }} />
            {invalidEnd && <small id={id + "-error"} role="alert">{copy.invalidEnd}</small>}
          </label>
        </div>
        {overlaps && <p className="stop-editor-overlap" role="status" id={id + "-overlap"}>{copy.overlap}</p>}
        <div className="stop-move-actions" role="group" aria-labelledby={id + "-order"}>
          <div>
            <span id={id + "-order"}>{copy.order}</span>
            <strong aria-live="polite">{copy.position(position + 1)}</strong>
          </div>
          <button type="button" aria-label={copy.up} disabled={busy || !canPreviewPosition(position - 1)}
            onClick={() => { setPosition(position - 1); setSubmitted(false); }}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-5 5 5-5 5 5" /></svg>
          </button>
          <button type="button" aria-label={copy.down} disabled={busy || !canPreviewPosition(position + 1)}
            onClick={() => { setPosition(position + 1); setSubmitted(false); }}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14m-5-5 5 5 5-5" /></svg>
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
        <div className="stop-time-actions">
          <button type="button" disabled={busy} onClick={onClose}>{copy.cancel}</button>
          <button type="submit" disabled={busy}>{copy.save}</button>
        </div>
      </form>
    </dialog>
  );
}
