// 일정 칸 사이 이동 안내 (GET /route 결과). 도보·버스·지하철 구간, 노선, 분, 승하차 정류장 표시
const copies = {
  ko: { label: "다음 장소까지 이동", total: (n) => `총 ${n}분`, minutes: (n) => `${n}분`, estimate: "추정", modes: { WALKING: "도보", BUS: "버스", SUBWAY: "지하철" }, other: "이동", ride: (from, to) => `${from} 승차 → ${to} 하차` },
  en: { label: "Travel to the next stop", total: (n) => `${n} min total`, minutes: (n) => `${n} min`, estimate: "estimate", modes: { WALKING: "Walk", BUS: "Bus", SUBWAY: "Subway" }, other: "Travel", ride: (from, to) => `Board at ${from} → get off at ${to}` },
  ja: { label: "次の場所への移動", total: (n) => `計${n}分`, minutes: (n) => `${n}分`, estimate: "推定", modes: { WALKING: "徒歩", BUS: "バス", SUBWAY: "地下鉄" }, other: "移動", ride: (from, to) => `${from}で乗車 → ${to}で下車` },
  "zh-Hans": { label: "前往下一地点", total: (n) => `共 ${n} 分钟`, minutes: (n) => `${n} 分钟`, estimate: "预计", modes: { WALKING: "步行", BUS: "公交", SUBWAY: "地铁" }, other: "移动", ride: (from, to) => `${from} 上车 → ${to} 下车` },
  "zh-Hant": { label: "前往下一地點", total: (n) => `共 ${n} 分鐘`, minutes: (n) => `${n} 分鐘`, estimate: "預估", modes: { WALKING: "步行", BUS: "公車", SUBWAY: "捷運" }, other: "移動", ride: (from, to) => `${from} 上車 → ${to} 下車` },
};

const ICONS = { WALKING: "🚶", BUS: "🚌", SUBWAY: "🚇" };

export default function TransitLeg({ route, language }) {
  if (!route?.segments?.length || !(route.minutes > 0)) return null; // 같은 장소 재방문 등 이동 없음
  const copy = copies[language] ?? copies.en;
  const estimated = route.source === "straight";
  // 직선 대체(조회 실패): 구간 대신 도보 또는 이동 추정 시간만 표시
  const parts = estimated
    ? [{ mode: route.mode === "walk" ? "WALKING" : "ESTIMATE", lines: [], minutes: route.minutes }]
    : route.segments.filter((part) => part.minutes > 0 || part.mode !== "WALKING");
  const rides = parts.filter((part) => part.mode !== "WALKING" && part.from_name && part.to_name);
  return (
    <div className="transit-leg" aria-label={copy.label} data-mode={route.mode}>
      <p className="transit-leg__summary">
        {parts.map((part, index) => (
          <span key={index} className="transit-leg__part" data-mode={part.mode}>
            <span aria-hidden="true">{ICONS[part.mode] ?? "➜"}</span>
            {copy.modes[part.mode] ?? copy.other}
            {part.lines?.length > 0 && <strong>{part.lines.slice(0, 2).join(", ")}</strong>}
            {copy.minutes(part.minutes)}
          </span>
        ))}
        {estimated ? <span className="transit-leg__estimate">({copy.estimate})</span>
          : <span className="transit-leg__total">{copy.total(route.minutes)}</span>}
      </p>
      {rides.map((part, index) => <p key={index} className="transit-leg__ride">{copy.ride(part.from_name, part.to_name)}</p>)}
    </div>
  );
}
