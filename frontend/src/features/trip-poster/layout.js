export const WIDTH = 540;
export const HEIGHT = 675;

function lowerRightCollage(count, tileWidth, tileHeight, shiftUp, keepRouteAbove) {
  const gap = 10;
  const columns = Math.min(count, 2);
  const rows = Math.ceil(count / columns);
  const width = columns * tileWidth + (columns - 1) * gap;
  const height = rows * tileHeight + (rows - 1) * gap;
  const x = WIDTH - 22 - width;
  const y = 614 - height - shiftUp;
  const guard = 48;

  return {
    padding: {
      left: 60,
      right: keepRouteAbove ? 60 : WIDTH - x + guard,
      top: 143,
      bottom: keepRouteAbove ? HEIGHT - y + guard : 88,
    },
    photos: Array.from({ length: count }, (_, index) => ({
      x: x + (index % columns) * (tileWidth + gap),
      y: y + Math.floor(index / columns) * (tileHeight + gap),
      w: tileWidth,
      h: tileHeight,
    })),
  };
}

export function posterLayouts(count) {
  if (!count) return [{ padding: { left: 62, right: 62, top: 143, bottom: 88 }, photos: [] }];

  return [
    lowerRightCollage(count, 126, 97, 0, true),
    lowerRightCollage(count, 117, 92, 15, false),
    lowerRightCollage(count, 105, 80, 0, true),
  ];
}
