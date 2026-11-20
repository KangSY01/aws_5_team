const seoulOffset = 9 * 60 * 60 * 1000;

function seoulTimestamp(milliseconds) {
  return new Date(milliseconds + seoulOffset).toISOString().slice(0, -1) + "+09:00";
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
