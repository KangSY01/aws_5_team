"""Bedrock 토큰 비교 실험: 전체 일정 재생성(기준) vs 부분 수정(edit 모드) vs Guardian 점검(규칙 기반).

같은 일정(app/data/sample_plan.json, 2026-11-21, ja, s2 고정)과 같은 변경 조건(15~17시 비)으로 세 방식을 돌린다.
기존 일정을 만드는 데 쓴 토큰은 어느 쪽에도 넣지 않는다 (일정은 샘플 파일에서 읽는다).

  A. full_regen  : 일정이 없는 세션(create 모드)에 CURRENT_PLAN 과 변경 조건을 주고 "일정 전체를 다시 만들어 달라"고 한다.
                   서비스에 전체 재생성 기능은 없으므로, 운영 코드의 create 모드(search_places → create_plan)를 그대로 쓴다.
  B. partial_edit: 일정이 연결된 세션(edit 모드)에 같은 변경 조건을 준다. 운영 코드의 부분 수정 도구(replace/move/...)를 쓴다.
  G. guardian    : POST /plan/check 와 같은 run_check (LLM 미사용). Bedrock 호출 수를 실제로 세서 기록한다.

토큰은 운영 코드가 남기는 BEDROCK_TOKEN_USAGE 로그(app/chat/token_usage.py)에서 읽는다. 값을 추정하거나 만들지 않는다.
실패한 회차(예: invalid_model_output)의 토큰도 기록하지만, 절감률은 응답까지 성공한 회차의 평균끼리만 계산한다.
어느 한쪽에 성공 회차가 없으면 N/A 다. 실패 원인은 app.agent 의 ERROR 로그 문장(장소 ID·오류 종류)으로 함께 보여 준다.
Bedrock API 호출 수는 botocore 호출을 직접 세어 로그의 bedrock_calls 와 맞춰 본다.

환경: USE_MOCK=1(샘플 데이터), STORAGE_BACKEND=memory(로컬 메모리), DEMO_CACHE_ENABLED=false 를 이 스크립트가 강제한다.
AWS 리소스를 만들거나 바꾸지 않는다. 실제 실행은 Bedrock 을 부르므로 요금이 발생한다.

실행 (backend/ 에서):
  uv run python -m scripts.token_compare --dry-run                 # Bedrock 없이 시나리오·Guardian 만 확인
  uv run --env-file .env python -m scripts.token_compare --runs 5  # 실제 측정 (Bedrock 호출)
"""

import argparse
import json
import logging
import os
import statistics
import sys
from pathlib import Path

# app.config 는 import 때 환경 변수를 읽으므로 app 을 불러오기 전에 정한다
os.environ["USE_MOCK"] = "1"
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["DEMO_CACHE_ENABLED"] = "false"

import botocore.client  # noqa: E402

from app import agent, config, storage  # noqa: E402
from app.chat import token_usage  # noqa: E402
from app.guardian.service import run_check  # noqa: E402
from app.models.api import ChatRequest, DemoOverride  # noqa: E402
from app.models.plan import Plan  # noqa: E402
from app.chat.plan_rules import load_places  # noqa: E402
from app.prompts import plan_view  # noqa: E402

PLAN_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "sample_plan.json"
DEMO_NOW = "2026-11-21T09:00:00+09:00"
# 두 방식에 똑같이 들어가는 변경 조건 (사용자 언어 ja = 샘플 일정의 프로필)
CONDITION = "11月21日は15時から17時まで雨の予報です。雨でも楽しめるように日程を調整してください。"
# 기준 방식에만 붙는 문장. create 모드에서 답변의 [place:ID] 근거는 이번 턴의 도구 결과와 새로 만든 일정뿐이다
# (agent._finish → answer.render_answer). 사용자 메시지로 준 CURRENT_PLAN 은 근거가 아니므로, 새 일정에 넣지 않은
# 예전 장소를 답변에 쓰면 운영 검증이 invalid_model_output 으로 막는다 (1회차 실행: gamcheon-village, haeundae-beach).
# 검증은 그대로 두고, 새 일정에 넣은 장소만 쓰라고 요청 문장에서 알린다. 예전 장소를 다시 쓰려면 search_places 로 찾아야 한다
REGEN_SUFFIX = (
    "日程全体を新しく作り直してください。"
    "回答では新しい日程に入れた場所だけを書き、新しい日程に入れない以前の場所には名前も含めて触れないでください。"
    "以前の場所を新しい日程に残す場合も、search_places で見つけてから create_plan に入れてください。"
)
BEDROCK_OPERATIONS = {"Converse", "ConverseStream", "InvokeModel", "InvokeModelWithResponseStream"}


class _UsageCapture(logging.Handler):
    """BEDROCK_TOKEN_USAGE 로그의 extra 값을 모은다."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None) == token_usage.EVENT:
            self.records.append({k: getattr(record, k) for k in (
                "operation", "input_tokens", "output_tokens", "total_tokens", "bedrock_calls", "stop_reason")})


class _ErrorCapture(logging.Handler):
    """app.agent 의 ERROR 로그 문장을 모은다 (실패 원인 분석용). 이 로그에는 장소 ID·오류 종류만 들어 있고 메시지는 없다."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class _BedrockCounter:
    """botocore 의 Bedrock 런타임 API 호출을 센다 (요청 내용은 보지 않는다)."""

    def __init__(self):
        self.count = 0
        self._original = botocore.client.BaseClient._make_api_call

    def __enter__(self):
        counter, original = self, self._original

        def counted(client, operation_name, api_params):
            if operation_name in BEDROCK_OPERATIONS:
                counter.count += 1
            return original(client, operation_name, api_params)

        botocore.client.BaseClient._make_api_call = counted
        return self

    def __exit__(self, *exc):
        botocore.client.BaseClient._make_api_call = self._original


def _load_plan() -> Plan:
    return Plan.model_validate_json(PLAN_PATH.read_text(encoding="utf-8"))


def _regen_message(plan: Plan) -> str:
    """기준 방식의 메시지. edit 모드 시스템 프롬프트의 CURRENT_PLAN 과 같은 내용을 사용자 메시지로 준다."""
    current = json.dumps(plan_view(plan, plan.profile.language), ensure_ascii=False)
    return f"CURRENT_PLAN: {current}\n{CONDITION}{REGEN_SUFFIX}"


def _preservation(original: Plan, final: Plan) -> dict:
    """원래 일정 대비 유지 정도. 장소가 같고 시각도 같으면 '그대로', 장소만 남으면 '장소 유지'로 센다."""
    before = {s.place_id: (s.start, s.end) for s in original.stops}
    after = {s.place_id: (s.start, s.end) for s in final.stops}
    locked = [s for s in original.stops if s.locked]
    return {
        "stops_after": len(final.stops),
        "places_kept": len(before.keys() & after.keys()),
        "stops_unchanged": sum(after.get(pid) == times for pid, times in before.items()),
        "locked_kept": all(after.get(s.place_id) == (s.start, s.end) for s in locked),
    }


def _chat_once(method: str, plan: Plan, capture: _UsageCapture, errors: _ErrorCapture) -> dict:
    """대화 한 건. 매번 메모리 저장소를 처음 상태(샘플 일정)로 되돌려 같은 일정에서 시작한다."""
    storage.reset_mock_store()
    if method == "full_regen":
        request = ChatRequest(message=_regen_message(plan), profile=plan.profile, demo={"now": DEMO_NOW})
    else:
        request = ChatRequest(message=CONDITION, profile=plan.profile, plan_id=plan.plan_id, demo={"now": DEMO_NOW})
    before, errors_before = len(capture.records), len(errors.messages)
    row: dict = {"method": method, "outcome": "ok"}
    with _BedrockCounter() as counter:
        try:
            response = agent.run_chat(request)
            row["plan_changes"] = len(response.plan_changes)
            row.update(_preservation(plan, storage.get_plan(response.plan_id)))  # 저장된 결과 일정 (메모리 저장소)
        except agent.ChatError as error:  # 실패해도 쓴 토큰은 로그로 남는다
            row["outcome"] = f"error:{error.code}"
    row["api_calls"] = counter.count
    if row["outcome"] != "ok":
        row["error_detail"] = errors.messages[errors_before:]
    logged = capture.records[before:]
    if len(logged) != 1:
        row["outcome"] += "/usage_missing"
        return row
    return {**row, **logged[0]}


def _guardian_once(plan: Plan) -> dict:
    with _BedrockCounter() as counter:
        result = run_check(plan, DemoOverride(now=DEMO_NOW))
    return {
        "method": "guardian", "outcome": "ok", "operation": "plan_check", "input_tokens": 0, "output_tokens": 0,
        "total_tokens": 0, "bedrock_calls": counter.count, "api_calls": counter.count,
        "issues": [f"{i.stop_id}:{i.type}" for i in result.issues],
        "repairs": sum(len(v) for v in result.repairs.values()),
    }


def _mean(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), int)]
    return statistics.mean(values) if values else None


TOKEN_KEYS = ("input_tokens", "output_tokens", "total_tokens", "bedrock_calls")


def _averages(rows: list[dict]) -> dict:
    return {"n": len(rows), **{f"avg_{k}": _mean(rows, k) for k in TOKEN_KEYS}}


def _summary(rows: list[dict]) -> dict:
    """all: 토큰이 기록된 모든 회차(실패 포함, 참고용). success: 응답까지 정상으로 끝난 회차만 (절감률 계산용)."""
    measured = [r for r in rows if "total_tokens" in r]
    return {
        "runs": len(rows),
        "all": _averages(measured),
        "success": _averages([r for r in measured if r["outcome"] == "ok"]),
        "failures": [r["outcome"] for r in rows if r["outcome"] != "ok"],
    }


def _reduction(baseline: float | None, optimized: float | None) -> float | None:
    if not baseline or optimized is None:  # 기준 측정값이 없으면 계산하지 않는다
        return None
    return (baseline - optimized) / baseline * 100


def _fmt(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:,.{digits}f}"


def _rates(summaries: dict, group: str) -> dict:
    base = summaries["full_regen"][group]["avg_total_tokens"]
    return {
        "partial_edit_vs_full_regen": _reduction(base, summaries["partial_edit"][group]["avg_total_tokens"]),
        "guardian_vs_full_regen": _reduction(base, summaries["guardian"][group]["avg_total_tokens"]),
    }


def _rate_text(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate:.1f}%"


def _print_table(summaries: dict, group: str) -> None:
    print(f"  {'방식':12s} {'회차':>5s} {'입력':>10s} {'출력':>10s} {'합계':>10s} {'Bedrock 호출':>12s}")
    for name, s in summaries.items():
        a = s[group]
        print(f"  {name:12s} {a['n']:>2d}/{s['runs']:<2d} {_fmt(a['avg_input_tokens']):>10s} {_fmt(a['avg_output_tokens']):>10s} "
              f"{_fmt(a['avg_total_tokens']):>10s} {_fmt(a['avg_bedrock_calls'], 2):>12s}")


def _print_report(results: dict[str, list[dict]]) -> dict:
    summaries = {name: _summary(rows) for name, rows in results.items()}
    print("\n[회차별]")
    for name, rows in results.items():
        for i, r in enumerate(rows, 1):
            kept = (f" 유지 장소={r['places_kept']} 시각까지 그대로={r['stops_unchanged']} 고정 유지={r['locked_kept']}"
                    if "places_kept" in r else "")
            print(f"  {name:12s} #{i}: 결과={r['outcome']} 입력={r.get('input_tokens', '-')} 출력={r.get('output_tokens', '-')} "
                  f"합계={r.get('total_tokens', '-')} 모델 호출={r.get('bedrock_calls', '-')} API 호출={r['api_calls']}"
                  f" plan_changes={r.get('plan_changes', '-')}{kept}")
            for detail in r.get("error_detail", []):
                print(f"      실패 원인 로그: {detail}")
    print("\n[평균 - 성공한 회차만] 절감률은 이 표로 계산한다")
    _print_table(summaries, "success")
    print("\n[평균 - 실패 포함 전체 회차] 참고용. 실패한 회차의 토큰도 실제로 쓴 값이다")
    _print_table(summaries, "all")

    success_rates, all_rates = _rates(summaries, "success"), _rates(summaries, "all")
    print("\n[절감률] (baseline - optimized) / baseline * 100, 총 토큰 평균")
    for key in success_rates:
        print(f"  {key}: 성공 회차끼리 {_rate_text(success_rates[key])}  (참고: 실패 포함 {_rate_text(all_rates[key])})")
    if success_rates["partial_edit_vs_full_regen"] is None:
        print("  성공한 전체 재생성 또는 부분 수정 회차가 없어 비교 가능한 절감률이 없습니다 (N/A).")
    return {"summaries": summaries, "reduction_rate_pct": {"success_only": success_rates, "including_failures": all_rates}}


def _print_environment(plan: Plan) -> None:
    """두 방식이 같은 데이터·제약에서 도는지 보여 준다. 운영 코드의 값을 읽기만 한다."""
    regen = agent._prepare(ChatRequest(message="x", profile=plan.profile, demo={"now": DEMO_NOW}))
    edit = agent._prepare(ChatRequest(message="x", profile=plan.profile, plan_id=plan.plan_id, demo={"now": DEMO_NOW}))
    storage.reset_mock_store()
    print("[비교 환경]")
    print(f"  모드: full_regen={regen.mode} partial_edit={edit.mode} / TODAY: {regen.today} = {edit.today}")
    print(f"  데이터: USE_MOCK={int(config.USE_MOCK)} places.json {len(load_places())}곳 (두 방식 같은 파일) / "
          f"도구 한도 {agent.MAX_TOOL_CALLS}회, 턴 한도 {agent.MAX_TURNS}, 대화 한도 {agent.CHAT_TIMEOUT_SEC}초 (같은 값)")
    print(f"  출력 상한(운영 값 그대로): create {agent.MAX_TOKENS} / edit {agent.EDIT_MAX_TOKENS} 토큰. "
          "상한일 뿐 실제 사용량은 모델 출력 길이다")
    print("  같은 정보: 일정(CURRENT_PLAN, locked 포함), 프로필, 변경 조건. full_regen 은 사용자 메시지로, "
          "partial_edit 는 시스템 프롬프트로 받는다")
    print("  다른 점: full_regen 의 create_plan 은 시각을 build_plan 이 새로 정해 locked 시각을 보장하지 않는다 (유지 지표로 기록)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bedrock 토큰 비교: 전체 재생성 vs 부분 수정 vs Guardian")
    parser.add_argument("--runs", type=int, default=5, help="방식마다 반복 횟수 (기본 5)")
    parser.add_argument("--dry-run", action="store_true", help="Bedrock 을 부르지 않고 시나리오와 Guardian 만 확인")
    parser.add_argument("--chat-timeout", type=float, default=None,
                        help="대화 한도(초). 기본은 운영 값 agent.CHAT_TIMEOUT_SEC. 두 방식에 같은 값이 적용된다")
    parser.add_argument("--out", type=Path, default=None, help="결과 JSON 저장 경로 (선택)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    capture = _UsageCapture()
    usage_logger = logging.getLogger(token_usage.__name__)
    usage_logger.setLevel(logging.INFO)
    usage_logger.addHandler(capture)
    usage_logger.propagate = False  # 화면에는 표로만 보여 준다
    errors = _ErrorCapture()
    logging.getLogger(agent.__name__).addHandler(errors)

    plan = _load_plan()
    print(f"시나리오: plan={plan.plan_id} date={plan.date} language={plan.profile.language} "
          f"stops={len(plan.stops)} locked={[s.stop_id for s in plan.stops if s.locked]} now={DEMO_NOW}")
    print(f"변경 조건: {CONDITION}")
    _print_environment(plan)
    results: dict[str, list[dict]] = {"guardian": [_guardian_once(plan) for _ in range(args.runs)]}
    print(f"Guardian 점검: issues={results['guardian'][0]['issues']} 해결안={results['guardian'][0]['repairs']}개 "
          f"Bedrock API 호출={results['guardian'][0]['api_calls']}회")

    if args.dry_run:
        print("\n--dry-run: Bedrock 을 부르지 않았습니다. 전체 재생성·부분 수정의 측정값은 없습니다.")
        print(f"전체 재생성 메시지 길이: {len(_regen_message(plan))}자, 부분 수정 메시지 길이: {len(CONDITION)}자")
        return 0

    if config.FAKE_LLM:
        print("FAKE_LLM=1 이면 Bedrock 을 부르지 않아 토큰을 잴 수 없습니다. FAKE_LLM=0 으로 실행해 주세요.", file=sys.stderr)
        return 2
    if args.chat_timeout:
        agent.CHAT_TIMEOUT_SEC = args.chat_timeout
    print(f"모델: {config.MODEL_ID} / 리전: {config.BEDROCK_REGION} / 대화 한도: {agent.CHAT_TIMEOUT_SEC}초 / 반복: {args.runs}회")

    results["full_regen"], results["partial_edit"] = [], []
    for i in range(args.runs):  # 두 방식을 번갈아 돌려 시간대에 따른 차이를 줄인다
        for method in ("full_regen", "partial_edit"):
            row = _chat_once(method, plan, capture, errors)
            results[method].append(row)
            print(f"  {i + 1}/{args.runs} {method}: {row['outcome']} 합계={row.get('total_tokens', '-')}")

    report = _print_report({k: results[k] for k in ("full_regen", "partial_edit", "guardian")})
    if args.out:
        args.out.write_text(json.dumps({"model_id": config.MODEL_ID, "scenario": {
            "plan_id": plan.plan_id, "date": plan.date.isoformat(), "now": DEMO_NOW, "condition": CONDITION},
            "runs": results, **report}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
