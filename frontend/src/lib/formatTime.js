// ISO 8601 문자열을 Asia/Seoul 기준 HH:mm 으로 변환하는 유틸리티

const FALLBACK = '--:--';

// YYYY-MM-DDTHH:mm 로 시작, 선택적 초/소수초 및 Z 또는 ±HH:mm
const ISO_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/;

// 모듈 수준에서 한 번만 생성. h23 으로 자정이 24:00 으로 표시되는 것을 방지
const formatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

export function formatTime(iso) {
  try {
    if (typeof iso !== 'string' || !ISO_PATTERN.test(iso)) return FALLBACK;
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return FALLBACK;
    const parts = formatter.formatToParts(new Date(ms));
    const hour = parts.find((p) => p.type === 'hour')?.value;
    const minute = parts.find((p) => p.type === 'minute')?.value;
    if (!hour || !minute) return FALLBACK;
    return `${hour}:${minute}`;
  } catch {
    return FALLBACK;
  }
}

export default formatTime;
