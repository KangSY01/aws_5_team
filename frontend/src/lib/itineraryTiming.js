const seoulOffset = 9 * 60 * 60 * 1000;

export function getTripStop(stops, now) {
  let current = null;
  let upcoming = null;
  let nextStart = Infinity;
  for (const stop of stops) {
    const start = Date.parse(stop.start);
    const end = Date.parse(stop.end);
    if (!(start < end)) continue;
    if (start <= now && now < end) current ??= stop;
    if (now < start && start < nextStart) {
      upcoming = stop;
      nextStart = start;
    }
  }
  return current ?? upcoming;
}

function seoulTimestamp(milliseconds) {
  return new Date(milliseconds + seoulOffset).toISOString().slice(0, -1) + "+09:00";
}

export function insertStopAfter(stops, index, placeId, startMinutes, firstDay, duration = 45) {
  const previous = stops[index];
  if (!previous && !(index === -1 && firstDay && startMinutes)) return null;
  const minute = 60_000;
  const day = previous ? stopDate(previous.start) : firstDay;
  const midnight = Date.parse(day + "T00:00:00+09:00");
  const earliest = previous ? Math.ceil(Date.parse(previous.end) / minute) * minute + 30 * minute : midnight;
  const start = startMinutes
    ? startMinutes.map((value) => midnight + value * minute).find((time) => time >= earliest)
    : earliest;
  const end = start + duration * minute;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || stopDate(seoulTimestamp(end)) !== day) return null;
  const following = stops[index + 1];
  if (following && !(end + 30 * minute <= Date.parse(following.start))) return null;
  if (stops.some((stop) => start < Date.parse(stop.end) && Date.parse(stop.start) < end)) return null;
  const added = { stop_id: crypto.randomUUID(), place_id: placeId, start: seoulTimestamp(start), end: seoulTimestamp(end), locked: false };
  return [...stops.slice(0, index + 1), added, ...stops.slice(index + 1)];
}

export function insertUnselectedStop(plan, placeId, startMinutes, duration) {
  const { stops } = plan;
  if (!startMinutes) return insertStopAfter(stops, stops.length - 1, placeId);
  const day = plan.date || stopDate(stops[0].start);
  const start = [startMinutes.at(-1)];
  const timestamp = Date.parse(day + "T00:00:00+09:00") + start[0] * 60_000;
  const firstFollowingStop = stops.findIndex((stop) => Date.parse(stop.start) > timestamp);
  const anchor = firstFollowingStop < 0 ? stops.length - 1 : firstFollowingStop - 1;
  if (anchor >= 0 && stopDate(stops[anchor].start) !== day) return null;
  return insertStopAfter(stops, anchor, placeId, start, day, duration);
}

export function suggestLaterStop(plan, placeId, startMinutes, anchorIndex) {
  if (!startMinutes) return null;
  const anchor = plan.stops[anchorIndex];
  const day = anchor ? stopDate(anchor.start) : plan.date;
  const midnight = Date.parse(day + "T00:00:00+09:00");
  const requested = startMinutes.at(-1);
  const stops = anchor ? [anchor] : plan.stops;
  const laterStarts = stops.filter((stop) => stopDate(stop.start) === day)
    .map((stop) => Math.ceil((Date.parse(stop.end) - midnight) / 60_000) + 30)
    .filter((minute) => minute > requested && minute < 24 * 60)
    .sort((a, b) => a - b);
  for (const minute of laterStarts) {
    const inserted = anchor
      ? insertStopAfter(plan.stops, anchorIndex, placeId, [minute])
      : insertUnselectedStop(plan, placeId, [minute]);
    if (inserted) return inserted.find((stop) => !plan.stops.includes(stop));
  }
  return null;
}

export function stopDate(timestamp) {
  const milliseconds = Date.parse(timestamp);
  return Number.isFinite(milliseconds) ? seoulTimestamp(milliseconds).slice(0, 10) : timestamp.slice(0, 10);
}

export function canMoveStop(stops, from, to) {
  const stop = stops[from];
  if (!stop || !stops[to] || from === to) return false;
  const day = stopDate(stop.start);
  return stops.slice(Math.min(from, to), Math.max(from, to) + 1)
    .every((item) => !item.locked && stopDate(item.start) === day &&
      Date.parse(item.end) > Date.parse(item.start));
}

export function reorderStops(stops, from, to) {
  if (!canMoveStop(stops, from, to)) return stops;
  const first = Math.min(from, to);
  const last = Math.max(from, to);
  const segment = stops.slice(first, last + 1);
  const slots = segment.map((stop) => stop.start).sort((a, b) => Date.parse(a) - Date.parse(b));
  const [moved] = segment.splice(from - first, 1);
  segment.splice(to - first, 0, moved);
  const rescheduled = segment.map((stop, index) => {
    const start = slots[index];
    if (Date.parse(start) === Date.parse(stop.start)) return stop;
    const duration = Date.parse(stop.end) - Date.parse(stop.start);
    return { ...stop, start, end: seoulTimestamp(Date.parse(start) + duration) };
  });
  return [...stops.slice(0, first), ...rescheduled, ...stops.slice(last + 1)];
}

export function overlappingStops(stops) {
  const overlaps = new Set();
  const intervals = stops.map(({ start, end }) => [Date.parse(start), Date.parse(end)]);
  intervals.forEach(([start, end], index) => {
    if (!(start < end)) return;
    for (let other = index + 1; other < intervals.length; other += 1) {
      const [otherStart, otherEnd] = intervals[other];
      if (otherStart < otherEnd && start < otherEnd && otherStart < end) {
        overlaps.add(index);
        overlaps.add(other);
      }
    }
  });
  return overlaps;
}
