import { useSyncExternalStore } from "react";
import { getDemoState, subscribeDemo } from "./demoStore.js";

// 데모 스위치 상태를 컴포넌트에서 읽는다. 값이 바뀌면 다시 그린다.
// 배지 다시 점검처럼 데모 값이 바뀔 때 할 일이 있으면 이 값을 useEffect 의존성에 넣는다.
export function useDemoSwitch() {
  return useSyncExternalStore(subscribeDemo, getDemoState, getDemoState);
}
