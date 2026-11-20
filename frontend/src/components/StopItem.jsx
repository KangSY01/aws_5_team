// 일정 한 항목: 시각 범위, 장소명, 고정 배지, 이름 대체 보조 문구
import { formatTime } from '../lib/formatTime.js';
import { resolvePlaceName } from '../lib/resolvePlaceName.js';
import { LOCKED_LABEL, PLACE_NAME_FALLBACK_NOTE } from '../constants/messages.js';

const SUPPORTED_LANGUAGES = ['ko', 'en', 'ja', 'zh-Hans', 'zh-Hant'];

// 잠금 아이콘 (장식용이므로 보조기기에서 숨긴다)
function LockIcon({ locked }) {
  return (
    <svg
      className="stop-item__locked-icon"
      aria-hidden="true"
      focusable="false"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d={locked ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-2"} />
      <path d="M12 15v2" />
    </svg>
  );
}

export default function StopItem({ stop, place, language, number, active, tripTarget, onSelect, lockedLabel = LOCKED_LABEL, onEdit, editLabel, day, formatStopDate, timing, overlap, dragging, insertion, checks, lock, eventName = "", checked }) {
  // resolvePlaceName 은 Map 을 받으므로 단일 장소를 Map 으로 감싸 전달한다
  const placesById = place ? new Map([[stop.place_id, place]]) : new Map();
  const { name, isFallbackToId } = resolvePlaceName(stop, placesById, language);
  const lang = SUPPORTED_LANGUAGES.includes(language) ? language : 'en';

  const time = (
    <>
      <time dateTime={stop.start}>{formatTime(stop.start)}</time>
      {' – '}
      <time dateTime={stop.end}>{formatTime(stop.end)}</time>
    </>
  );
  const content = (
    <>
      {number != null && (
        <span className="stop-number" data-drag-handle={timing?.hint ? '' : undefined} title={timing?.hint}
          {...(timing?.hint ? timing.handle : undefined)}>{number}</span>
      )}
      {checked !== undefined && <span className="stop-check" data-checked={checked} aria-hidden="true" />}
      {!timing && <span className="stop-item__time">{time}</span>}
      {/* 이름이 place_id 로 대체되면 lang 을 붙이지 않는다. 텍스트로만 출력한다 */}
      <span
        className="stop-item__name"
        {...(isFallbackToId ? {} : { lang })}
      >
        {name}
      </span>
      {eventName && <span className="stop-item__event" lang={lang}>{eventName}</span>}
      {stop.locked === true && !lock && (
        <span className="stop-item__locked">
          <LockIcon locked />
          <span>{lockedLabel}</span>
        </span>
      )}
      {overlap && <span className="stop-overlap">{overlap}</span>}
      {isFallbackToId && !onSelect && (
        <span className="stop-item__note">{PLACE_NAME_FALLBACK_NOTE}</span>
      )}
    </>
  );
  return (
    <li className="stop-item" data-insert={insertion}>
      {day && <h3 className="stop-day"><time dateTime={day}>{formatStopDate(day)}</time></h3>}
      {onSelect ? (
        <div className="stop-track">
          <div className="stop-row" data-editable-time={Boolean(timing)} data-has-lock={Boolean(lock)} data-dragging={dragging || undefined}>
            <button type="button" className="stop-select" aria-pressed={active} aria-current={tripTarget || undefined} onClick={onSelect}>
              {content}
            </button>
            {timing && (
              <button type="button" className="stop-time" disabled={timing.disabled}
                aria-label={timing.label + ' · ' + name + ' · ' + formatTime(stop.start) + ' – ' + formatTime(stop.end)}
                aria-haspopup="dialog" aria-description={timing.hint}
                onClick={timing.open}>
                <span>{time}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4-.8L20 7l-4-4L4.8 15z" /></svg>
              </button>
            )}
            {(lock || onEdit) && <div className="stop-actions">
              {lock && (
                <button type="button" className="stop-lock" aria-pressed={Boolean(stop.locked)}
                  aria-label={lock.label(name)} title={lock.label(name)} disabled={lock.disabled} onClick={lock.toggle}>
                  <LockIcon locked={stop.locked} />
                  {stop.locked && <span>{lockedLabel}</span>}
                </button>
              )}
              {onEdit && (
                <button type="button" className="stop-edit" aria-label={editLabel + " · " + name} onClick={onEdit}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 3c0 5-4 9-9 9 5 0 9 4 9 9 0-5 4-9 9-9-5 0-9-4-9-9Z" />
                  </svg>
                  <span>{editLabel}</span>
                </button>
              )}
            </div>}
            {checks}
          </div>
        </div>
      ) : content}
    </li>
  );
}
