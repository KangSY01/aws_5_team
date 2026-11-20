// 여행 진행도: 끝난 일정 수 / 전체, 진행 막대, 지금 머무는 곳 또는 다음 장소
const copies = {
  ko: { label: "여행 진행도", done: (n, total) => `${total}곳 중 ${n}곳 완료`, now: "지금", next: "다음", finished: "모든 일정을 마쳤어요" },
  en: { label: "Trip progress", done: (n, total) => `${n} of ${total} stops done`, now: "Now", next: "Next", finished: "All stops done" },
  ja: { label: "旅の進み具合", done: (n, total) => `${total}か所中${n}か所完了`, now: "現在", next: "次", finished: "すべての予定が終わりました" },
  "zh-Hans": { label: "行程进度", done: (n, total) => `已完成 ${n}/${total} 处`, now: "当前", next: "下一站", finished: "所有行程已完成" },
  "zh-Hant": { label: "行程進度", done: (n, total) => `已完成 ${n}/${total} 處`, now: "目前", next: "下一站", finished: "所有行程已完成" },
};

export default function TripProgress({ stops, now, current, currentName, language, formatTime }) {
  if (!stops.length) return null;
  const copy = copies[language] ?? copies.en;
  const done = stops.filter((stop) => Date.parse(stop.end) <= now).length;
  const staying = current && Date.parse(current.start) <= now;
  return (
    <section className="trip-progress" aria-label={copy.label}>
      <p className="trip-progress__count">{copy.done(done, stops.length)}</p>
      <div className="trip-progress__bar" role="progressbar" aria-label={copy.label}
        aria-valuemin={0} aria-valuemax={stops.length} aria-valuenow={done}>
        <span style={{ width: `${(done / stops.length) * 100}%` }} />
      </div>
      <p className="trip-progress__next">
        {current ? <><span>{staying ? copy.now : copy.next}</span> <strong>{currentName}</strong>
          {!staying && <time dateTime={current.start}> {formatTime(current.start)}</time>}</> : copy.finished}
      </p>
    </section>
  );
}
