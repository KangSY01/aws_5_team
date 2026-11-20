import { requestJson } from "./planClient.js";

export async function fetchPedestrianPaths(origin, destination, signal) {
  const point = ([lat, lng]) => ({ lat, lng });
  const result = await requestJson("/routes/pedestrian", {
    signal,
    request: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin: point(origin), destination: point(destination) }),
    },
  });
  const paths = result?.paths?.filter((line) => Array.isArray(line) && line.length >= 2 &&
    line.every((pair) => Array.isArray(pair) && pair.length === 2 &&
      pair.every(Number.isFinite) && Math.abs(pair[0]) <= 180 && Math.abs(pair[1]) <= 90));
  if (!paths?.length) throw new Error("No pedestrian geometry");
  return paths.map((line) => line.map(([lng, lat]) => [lat, lng]));
}
