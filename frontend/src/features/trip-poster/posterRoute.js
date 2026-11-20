const MAX_SNAP_DISTANCE_METERS = 60;

function distanceMeters([lng, lat], [otherLng, otherLat]) {
  return Math.hypot((lng - otherLng) * 111320 * Math.cos(lat * Math.PI / 180), (lat - otherLat) * 111320);
}

function nearestVertex(points, coordinate) {
  let index = -1;
  let distance = MAX_SNAP_DISTANCE_METERS;
  points.forEach((point, position) => {
    const gap = distanceMeters(point, coordinate);
    if (gap < distance) {
      index = position;
      distance = gap;
    }
  });
  return { index, distance };
}

export function posterRoute(stops, walkingRoute) {
  const saved = (Array.isArray(walkingRoute) ? walkingRoute : []).filter(Array.isArray)
    .map((segment) => segment.filter((point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite))
      .map(([lat, lng]) => [lng, lat])).filter((segment) => segment.length > 1);
  return stops.slice(1).map(({ coordinate: end }, index) => {
    const { coordinate: start } = stops[index];
    let match = null;
    for (const points of saved) {
      const from = nearestVertex(points, start);
      const to = nearestVertex(points, end);
      if (from.index < 0 || to.index < 0 || from.index === to.index) continue;
      const distance = from.distance + to.distance;
      if (match && match.distance <= distance) continue;
      const section = points.slice(Math.min(from.index, to.index), Math.max(from.index, to.index) + 1);
      if (from.index > to.index) section.reverse();
      match = { distance, section };
    }
    const points = match ? [start, ...match.section, end] : [start, end];
    return {
      points: points.filter(([lng, lat], i) => !i || lng !== points[i - 1][0] || lat !== points[i - 1][1]),
      saved: Boolean(match),
    };
  });
}
