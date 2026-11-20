import { useEffect, useRef, useState } from "react";
import { canMoveStop } from "../lib/itineraryTiming.js";

const holdDelay = 400;
const moveTolerance = 8;
const edgeSize = 36;

export function useStopDrag(list, stops, onMove) {
  const gesture = useRef(null);
  const suppressClick = useRef(false);
  const [drag, setDrag] = useState(null);

  function stopGesture() {
    const current = gesture.current;
    gesture.current = null;
    if (!current) return;
    clearTimeout(current.timer);
    cancelAnimationFrame(current.frame);
  }

  useEffect(() => stopGesture, []);

  function start(index, id, x, y, kind) {
    suppressClick.current = false;
    if (gesture.current || !onMove) return;
    let first = index;
    let last = index;
    while (canMoveStop(stops, index, first - 1)) first -= 1;
    while (canMoveStop(stops, index, last + 1)) last += 1;
    if (first === last) return;
    const scroller = list.current.closest(".chat-content");
    const current = { index, id, x, y, kind, stops, target: index, active: false };
    gesture.current = current;

    function track() {
      const bounds = scroller?.getBoundingClientRect();
      if (bounds) {
        const up = Math.max(0, bounds.top + edgeSize - current.y);
        const down = Math.max(0, current.y - bounds.bottom + edgeSize);
        scroller.scrollTop += Math.max(-16, Math.min(16, (down - up) / 3));
      }
      let distance = Infinity;
      let target = index;
      for (let candidate = first; candidate <= last; candidate += 1) {
        const row = list.current.children[candidate]?.querySelector(".stop-row")?.getBoundingClientRect();
        if (!row) continue;
        const gap = Math.abs(current.y - (row.top + row.bottom) / 2);
        if (gap < distance) {
          distance = gap;
          target = candidate;
        }
      }
      if (target !== current.target) {
        current.target = target;
        setDrag({ from: index, to: target });
      }
      current.frame = requestAnimationFrame(track);
    }

    current.timer = setTimeout(() => {
      current.active = true;
      suppressClick.current = true;
      setDrag({ from: index, to: index });
      current.frame = requestAnimationFrame(track);
    }, holdDelay);
  }

  function move(kind, id, x, y) {
    const current = gesture.current;
    if (!current || current.kind !== kind || current.id !== id) return false;
    if (!current.active) {
      if (Math.hypot(x - current.x, y - current.y) > moveTolerance) stopGesture();
      return false;
    }
    current.y = y;
    return true;
  }

  function finish(kind, id, commit) {
    const current = gesture.current;
    if (!current || current.kind !== kind || current.id !== id) return false;
    stopGesture();
    if (!current.active) return false;
    setDrag(null);
    if (commit && current.stops === stops && current.index !== current.target) onMove?.(current.index, current.target);
    return true;
  }

  useEffect(() => {
    const element = list.current;
    function touchMove(event) {
      const finger = [...event.changedTouches].find(({ identifier }) => identifier === gesture.current?.id);
      if (finger && move("touch", finger.identifier, finger.clientX, finger.clientY) && event.cancelable) {
        event.preventDefault();
      }
    }
    function touchFinish(event) {
      for (const { identifier } of event.changedTouches) {
        if (finish("touch", identifier, event.type === "touchend") && event.cancelable) event.preventDefault();
      }
    }
    element.addEventListener("touchmove", touchMove, { passive: false });
    element.addEventListener("touchend", touchFinish, { passive: false });
    element.addEventListener("touchcancel", touchFinish);
    return () => {
      element.removeEventListener("touchmove", touchMove);
      element.removeEventListener("touchend", touchFinish);
      element.removeEventListener("touchcancel", touchFinish);
    };
  });

  function handleProps(index) {
    return {
      onPointerDown(event) {
        suppressClick.current = false;
        if (event.pointerType === "touch" || event.button !== 0) return;
        start(index, event.pointerId, event.clientX, event.clientY, "pointer");
        if (gesture.current) event.currentTarget.setPointerCapture(event.pointerId);
      },
      onPointerMove: (event) => move("pointer", event.pointerId, event.clientX, event.clientY),
      onPointerUp: (event) => finish("pointer", event.pointerId, true),
      onLostPointerCapture: (event) => finish("pointer", event.pointerId, false),
      onTouchStart(event) {
        if (event.touches.length !== 1) {
          const current = gesture.current;
          if (current?.kind === "touch") finish("touch", current.id, false);
          return;
        }
        const finger = event.changedTouches[0];
        start(index, finger.identifier, finger.clientX, finger.clientY, "touch");
      },
      onContextMenu: (event) => event.preventDefault(),
      onClick(event) {
        if (suppressClick.current && event.detail > 0) event.stopPropagation();
        suppressClick.current = false;
      },
    };
  }

  function cancel(event) {
    const current = gesture.current;
    if (event.key === "Escape" && current) {
      event.stopPropagation();
      finish(current.kind, current.id, false);
    }
  }

  return { drag, handleProps, cancel };
}
