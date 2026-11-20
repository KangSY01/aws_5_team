// 일정(Plan)을 불러와 loading / success / empty / error 상태로 돌려주는 훅.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { fetchPlan, PlanClientError } from "../api/planClient.js";

const LOADING = { status: "loading" };

function reducer(state, action) {
  switch (action.type) {
    case "start":
      // 이미 loading 이면 같은 객체를 돌려 불필요한 렌더링을 피한다.
      return state.status === "loading" ? state : LOADING;
    case "success":
      return action.plan.stops.length === 0
        ? { status: "empty", plan: action.plan }
        : { status: "success", plan: action.plan, places: action.places };
    case "error":
      return { status: "error", error: action.error };
    default:
      return state;
  }
}

// PlanClientError 가 아닌 예외는 network 오류로 안전하게 바꾼다.
function toClientError(err) {
  if (err instanceof PlanClientError) return err;
  return new PlanClientError("network", { message: "네트워크 연결 실패" });
}

/**
 * @returns {{ state: object, retry: () => void }}
 * state: { status: "loading" } | { status: "success", plan, places }
 *      | { status: "empty", plan } | { status: "error", error }
 */
export function usePlan(planId = "plan-1") {
  const [state, dispatch] = useReducer(reducer, LOADING);
  const [attempt, setAttempt] = useState(0);
  // retry 가 같은 틱에 여러 번 불려도 한 번만 처리하도록 동기적으로 갱신하는 상태.
  const statusRef = useRef("loading");
  statusRef.current = state.status;

  useEffect(() => {
    const controller = new AbortController();
    dispatch({ type: "start" });

    (async () => {
      try {
        const { plan, places } = await fetchPlan(planId, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        dispatch({ type: "success", plan, places });
      } catch (err) {
        // 호출자 취소(언마운트·재요청)는 상태에 반영하지 않는다.
        if (controller.signal.aborted) return;
        const error = toClientError(err);
        // 종류와 HTTP 상태만 기록한다. 응답 본문·인증 정보·환경 변수는 기록하지 않는다.
        console.error(
          "[일정] 요청 실패: 종류=%s HTTP 상태=%s",
          error.kind,
          error.status ?? "없음",
        );
        dispatch({ type: "error", error });
      }
    })();

    // 언마운트 또는 재요청 시 진행 중인 요청을 취소한다.
    return () => controller.abort();
  }, [planId, attempt]);

  const retry = useCallback(() => {
    // 로딩 중에는 동시 요청이 생기지 않도록 아무것도 하지 않는다.
    if (statusRef.current === "loading") return;
    statusRef.current = "loading";
    dispatch({ type: "start" });
    setAttempt((n) => n + 1);
  }, []);

  return { state, retry };
}
