import { configureBusanMapWorker, loadBusanStyle } from "../../components/busanBasemap.js";
import { resolvePlaceName, buildPlacesById } from "../../lib/resolvePlaceName.js";
import { HEIGHT, WIDTH, posterLayouts } from "./layout.js";
import { posterRoute } from "./posterRoute.js";

const scale = 2;
const green = "#145440";
const ink = "#102e48";
const title = "부산네컷";
const titleFont = '700 41px "Busan Poster Title", "Batang", serif';

function waitForMap(map, signal) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => done(new Error("Map tiles timed out")), 20000);
    const idle = () => done();
    const abort = () => done(signal.reason);
    function done(error) {
      clearTimeout(timeout);
      map.off("idle", idle);
      signal.removeEventListener("abort", abort);
      if (error) reject(error);
      else resolve();
    }
    map.on("idle", idle);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    else map.triggerRepaint();
  });
}

function photoCanvas(ctx, bitmap, box) {
  const { x, y, w, h } = box;
  ctx.save();
  ctx.shadowColor = "#122f4238";
  ctx.shadowOffsetY = 2;
  ctx.shadowBlur = 4;
  ctx.fillStyle = "#fff";
  ctx.fillRect(x, y, w, h);
  ctx.restore();
  const border = 4;
  const width = w - border * 2;
  const height = h - border * 2;
  const ratio = Math.max(width / bitmap.width, height / bitmap.height);
  const sourceW = width / ratio;
  const sourceH = height / ratio;
  ctx.drawImage(bitmap, (bitmap.width - sourceW) / 2, (bitmap.height - sourceH) / 2,
    sourceW, sourceH, x + border, y + border, width, height);
}

function drawPin(ctx, point, anchor, number) {
  const { x, y } = point;
  if (anchor.x !== x || anchor.y !== y) {
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(anchor.x, anchor.y);
    ctx.lineTo(x, y);
    ctx.stroke();
  }
  ctx.save();
  ctx.translate(x - 17, y - 32);
  ctx.scale(34 / 44, 34 / 44);
  const path = new Path2D("M22 42C15 34 7 25 7 18a15 15 0 1 1 30 0c0 7-8 16-15 24Z");
  ctx.fillStyle = green;
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2.4;
  ctx.fill(path);
  ctx.stroke(path);
  ctx.fillStyle = "#fff";
  ctx.font = "bold 15px system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(number, 22, 18);
  ctx.restore();
}

function intersects(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function drawStops(ctx, map, stops, photos) {
  const avoid = [...photos, { x: 0, y: 0, w: WIDTH, h: 108 }, { x: 0, y: 630, w: WIDTH, h: 45 }];
  const inside = ({ x, y, w, h }) => x >= 8 && x + w <= WIDTH - 8 && y >= 110 && y + h < 630;
  const pinned = stops.map((stop) => {
    const anchor = map.project(stop.coordinate);
    const positions = [[0, 0], [-29, 0], [29, 0], [0, 32], [0, -32]];
    for (let distance = 38; distance <= 114; distance += 38) {
      positions.push([-distance, -distance], [distance, -distance], [-distance, distance], [distance, distance],
        [-distance, 0], [distance, 0], [0, -distance], [0, distance]);
    }
    for (const [dx, dy] of positions) {
      const point = { x: anchor.x + dx, y: anchor.y + dy };
      const rect = { x: point.x - 13, y: point.y - 32, w: 26, h: 33 };
      if (inside(rect) && !avoid.some((box) => intersects(box, rect))) {
        avoid.push(rect);
        return { ...stop, anchor, point };
      }
    }
    return { ...stop, anchor, point: anchor };
  });

  for (const { number, point, anchor } of pinned) drawPin(ctx, point, anchor, number);

  ctx.font = "700 12px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  for (const { name, point } of pinned) {
    const w = Math.min(152, ctx.measureText(name).width + 12);
    const { x, y } = point;
    const options = [
      { x: x + 15, y: y - 21, w, h: 19 },
      { x: x - w - 15, y: y - 21, w, h: 19 },
      { x: x - w / 2, y: y + 3, w, h: 19 },
      { x: x - w / 2, y: y - 54, w, h: 19 },
    ];
    const label = options.find((box) => inside(box) && !avoid.some((obstacle) => intersects(box, obstacle)));
    if (!label) continue;
    avoid.push(label);
    ctx.fillStyle = "#fffdf5";
    ctx.beginPath();
    ctx.roundRect(label.x, label.y, label.w, label.h, 4);
    ctx.fill();
    ctx.fillStyle = green;
    ctx.fillText(name, label.x + 6, label.y + label.h / 2, label.w - 12);
  }
}

function drawRoute(ctx, map, route) {
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.setLineDash([2, 5]);
  for (const { points, saved } of route) {
    ctx.strokeStyle = saved ? "#247d84" : "rgba(53,118,122,.62)";
    ctx.lineWidth = saved ? 2.6 : 1.35;
    ctx.beginPath();
    points.forEach((coordinate, index) => {
      const { x, y } = map.project(coordinate);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  ctx.restore();
}

function drawText(ctx, date, attribution) {
  const titleX = 29;
  const titleBaseline = 62;
  ctx.textBaseline = "alphabetic";
  ctx.font = titleFont;
  const titleBounds = ctx.measureText(title);
  const center = titleX + (titleBounds.actualBoundingBoxRight - titleBounds.actualBoundingBoxLeft) / 2;

  ctx.save();
  ctx.translate(center, 49);
  ctx.scale(1, .44);
  const wash = ctx.createRadialGradient(0, 0, 28, 0, 0, 122);
  wash.addColorStop(0, "rgba(255,255,255,.78)");
  wash.addColorStop(.55, "rgba(255,255,255,.62)");
  wash.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = wash;
  ctx.fillRect(-122, -122, 244, 244);
  ctx.restore();

  ctx.fillStyle = green;
  ctx.font = titleFont;
  ctx.fillText(title, titleX, titleBaseline);
  ctx.save();
  ctx.font = "500 11px system-ui, sans-serif";
  ctx.textAlign = "center";
  const dateBaseline = titleBaseline + titleBounds.actualBoundingBoxDescent + 7 + ctx.measureText(date).actualBoundingBoxAscent;
  ctx.fillText(date, center, dateBaseline);
  ctx.restore();

  ctx.fillStyle = "rgba(255,253,245,.94)";
  ctx.fillRect(0, 636, WIDTH, 39);
  ctx.fillStyle = green;
  ctx.font = "bold 20px Georgia, serif";
  ctx.fillText("BusanNow", 22, 661);
  ctx.fillStyle = ink;
  ctx.font = "10px system-ui";
  ctx.textAlign = "right";
  ctx.fillText(attribution, WIDTH - 18, 660, WIDTH - 145);
}

function suppressCoveredLabels(map, style, photos) {
  if (!photos.length) return;
  const exclusions = photos.map(({ x, y, w, h }) => {
    const margin = 42;
    const points = [[x-margin,y-margin], [x+w+margin,y-margin], [x+w+margin,y+h+margin], [x-margin,y+h+margin], [x-margin,y-margin]];
    return ["!", ["within", { type: "Polygon", coordinates: [points.map((point) => map.unproject(point).toArray())] }]];
  });
  for (const layer of style.layers.filter(({ type }) => type === "symbol")) {
    map.setFilter(layer.id, ["all", ...(layer.filter ? [layer.filter] : []), ...exclusions]);
  }
}

async function createBase(trip, count, language, signal) {
  const [{ Map: VectorMap, LngLatBounds }, style] = await Promise.all([import("maplibre-gl"), loadBusanStyle(signal)]);
  signal.throwIfAborted();
  configureBusanMapWorker();
  // The shared basemap is fetched fresh. Only the export map uses this city label.
  style.layers = style.layers.flatMap((layer) => {
    if (layer.type !== "symbol") return [layer];
    if (layer.id !== "regional-places") return [];
    return [{
      ...layer,
      filter: ["all", ["==", ["get", "class"], "city"], ["in", ["get", "name"], ["literal", ["부산", "부산광역시", "Busan"]]]],
      layout: { ...layer.layout, "text-field": "부산광역시" },
    }];
  });
  const places = buildPlacesById(trip.places);
  const stops = trip.stops.flatMap((stop, index) => {
    const place = places.get(stop.place_id);
    if (!Number.isFinite(place?.lat) || !Number.isFinite(place?.lng)) return [];
    return [{ coordinate: [place.lng, place.lat], number: index + 1, name: resolvePlaceName(stop, places, language).name }];
  });
  if (!stops.length) throw new Error("No mapped stops");
  const route = posterRoute(stops, trip.walkingRoute);
  const bounds = new LngLatBounds();
  [...stops.map(({ coordinate }) => coordinate), ...route.flatMap(({ points }) => points)]
    .forEach((point) => bounds.extend(point));
  const host = document.createElement("div");
  host.className = "poster-map-renderer";
  host.style.width = WIDTH + "px";
  host.style.height = HEIGHT + "px";
  document.body.append(host);
  let map;
  try {
    map = new VectorMap({
      container: host, style, interactive: false, attributionControl: false, pixelRatio: scale,
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    const choices = posterLayouts(count).map((layout) => ({
      ...layout, camera: map.cameraForBounds(bounds, { padding: layout.padding, maxZoom: 14 }),
    })).filter(({ camera }) => camera);
    const layout = choices.sort((a, b) => (b.camera.zoom + Math.log2((b.photos[0]?.w ?? 1) / 126) * .35) -
      (a.camera.zoom + Math.log2((a.photos[0]?.w ?? 1) / 126) * .35))[0];
    if (!layout) throw new Error("Unable to fit trip");
    map.jumpTo(layout.camera);
    await waitForMap(map, signal);
    if (!map.queryRenderedFeatures().some((feature) => feature.source === "openmaptiles")) throw new Error("Map tiles unavailable");
    suppressCoveredLabels(map, style, layout.photos);
    await waitForMap(map, signal);
    const canvas = document.createElement("canvas");
    canvas.width = WIDTH * scale;
    canvas.height = HEIGHT * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.drawImage(map.getCanvas(), 0, 0, WIDTH, HEIGHT);
    drawRoute(ctx, map, route);
    drawStops(ctx, map, stops, layout.photos);
    const attribution = Object.values(style.sources).map((source) => source.attribution).filter(Boolean).join(" · ");
    const credits = new DOMParser().parseFromString(attribution, "text/html").body.textContent;
    await document.fonts.load(titleFont, title);
    signal.throwIfAborted();
    drawText(ctx, new Intl.DateTimeFormat(language, { dateStyle: "medium", timeZone: "UTC" }).format(new Date(trip.date + "T00:00:00Z")), credits);
    return { canvas, slots: layout.photos };
  } finally {
    map?.remove();
    host.remove();
  }
}

export async function createPoster(trip, photos, language, signal, mapCache) {
  const key = language + ":" + photos.length;
  let base = mapCache.get(key);
  if (!base) {
    base = await createBase(trip, photos.length, language, signal);
    signal.throwIfAborted();
    mapCache.set(key, base);
  }
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH * scale;
  canvas.height = HEIGHT * scale;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(base.canvas, 0, 0);
  ctx.scale(scale, scale);
  for (const [index, file] of photos.entries()) {
    const bitmap = await createImageBitmap(file);
    try {
      signal.throwIfAborted();
      photoCanvas(ctx, bitmap, base.slots[index]);
    } finally {
      bitmap.close();
    }
  }
  return new Promise((resolve, reject) => canvas.toBlob((png) => png ? resolve(png) : reject(new Error("PNG export failed")), "image/png"));
}
