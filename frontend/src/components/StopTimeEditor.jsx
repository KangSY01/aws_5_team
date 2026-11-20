import { useId, useLayoutEffect, useRef, useState } from "react";
import { formatTime } from "../lib/formatTime.js";
import { stopDate } from "../lib/itineraryTiming.js";

export default function StopTimeEditor({ stop, name, copy, busy, error, formatStopDate, onClose, onSave, onUp, onDown }) {
  const dialog = useRef(null);
  const id = useId();
  const [start, setStart] = useState(() => formatTime(stop.start));
  const [end, setEnd] = useState(() => formatTime(stop.end));
  const [invalidEnd, setInvalidEnd] = useState(false);
  const endField = useRef(null);
  const startDay = stopDate(stop.start);
  const endDay = stopDate(stop.end);

  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const updatedStart = start === formatTime(stop.start) ? stop.start : startDay + "T" + start + ":00+09:00";
    const updatedEnd = end === formatTime(stop.end) ? stop.end : endDay + "T" + end + ":00+09:00";
    if (!(Date.parse(updatedEnd) > Date.parse(updatedStart))) {
      setInvalidEnd(true);
      endField.current.focus();
      return;
    }
    if (await onSave(updatedStart, updatedEnd)) onClose();
  }

  return (
    <dialog className="stop-time-dialog" ref={dialog} aria-labelledby={id}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <h2 id={id}>{copy.edit}</h2>
      <p>{name}</p>
      <form onSubmit={submit} aria-busy={busy}>
        <div className="stop-time-fields">
          <label>
            {copy.start}
            {startDay !== endDay && <small>{formatStopDate?.(startDay) ?? startDay}</small>}
            <input required type="time" value={start} onChange={(event) => { setStart(event.target.value); setInvalidEnd(false); }} />
          </label>
          <label>
            {copy.end}
            {startDay !== endDay && <small>{formatStopDate?.(endDay) ?? endDay}</small>}
            <input required type="time" value={end} ref={endField}
              aria-invalid={invalidEnd || undefined} aria-describedby={invalidEnd ? id + "-error" : undefined}
              onChange={(event) => { setEnd(event.target.value); setInvalidEnd(false); }} />
            {invalidEnd && <small id={id + "-error"} role="alert">{copy.invalidEnd}</small>}
          </label>
        </div>
        <div className="stop-time-actions">
          <button type="button" disabled={busy} onClick={onClose}>{copy.cancel}</button>
          <button type="submit" disabled={busy}>{copy.save}</button>
        </div>
      </form>
      {(onUp || onDown) && (
        <fieldset className="stop-move-actions">
          <legend>{copy.order}</legend>
          <button type="button" disabled={busy || !onUp} onClick={onUp}>{copy.up}</button>
          <button type="button" disabled={busy || !onDown} onClick={onDown}>{copy.down}</button>
        </fieldset>
      )}
      {error && <p role="alert">{error}</p>}
    </dialog>
  );
}
