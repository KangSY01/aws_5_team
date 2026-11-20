import { useEffect, useRef, useState } from "react";
import { fetchPedestrianPaths } from "../api/pedestrianClient.js";

const copy = {
  ko: ["귀가 경로", "도보 경로 보기", "도보 경로를 불러오지 못했어요.", "약 {n}분", "카카오 대중교통", "이동 시간 추정"],
  en: ["Return routes", "Show walking route", "Couldn’t load the walking route.", "About {n} min", "Kakao transit", "Estimated travel time"],
  ja: ["帰りのルート", "徒歩ルートを見る", "徒歩ルートを読み込めませんでした。", "約{n}分", "カカオ公共交通", "推定所要時間"],
  "zh-Hans": ["返程路线", "查看步行路线", "无法加载步行路线。", "约 {n} 分钟", "Kakao 公共交通", "预计出行时间"],
  "zh-Hant": ["返程路線", "查看步行路線", "無法載入步行路線。", "約 {n} 分鐘", "Kakao 大眾運輸", "預計行程時間"],
};

export default function ReturnRouteOptions({ routes, origin, language, onShow }) {
  const [title, show, failure, duration, transit, estimate] = copy[language];
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  const stationName = ({ names }) => names?.[language] ?? names?.ko ?? names?.en;
  const time = new Intl.DateTimeFormat(language, { hour: "numeric", minute: "2-digit", timeZone: "Asia/Seoul" });

  async function openWalk(station) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setError(false);
    setLoading(true);
    try {
      const paths = await fetchPedestrianPaths([origin.lat, origin.lng], [station.lat, station.lng], controller.signal);
      if (!controller.signal.aborted) onShow(paths);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setLoading(false);
      }
    }
  }

  return <section className="chat-bubble return-route-options" aria-label={title}>
    <strong>{title}</strong>
    <ul>
      {routes.options.map(({ station, travel_min: minutes, depart_at: depart, time_source: source }, index) =>
        <li key={index}>
          <strong>{stationName(station)} → {stationName(routes.destination)}</strong>
          <p>{time.format(new Date(depart))} · {duration.replace("{n}", minutes)} · {source === "kakao" ? transit : estimate}</p>
          {origin && <button type="button" disabled={loading} onClick={() => openWalk(station)}>{show}</button>}
        </li>)}
    </ul>
    {error && <p role="alert">{failure}</p>}
  </section>;
}
