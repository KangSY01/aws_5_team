"""데모 장면 1·2·5·7의 도구와 주요 handler 경로를 네트워크 없이 한 번씩 점검한다.

    uv run python -m scripts.demo_offline_check

스크립트가 USE_MOCK=1, FAKE_LLM=1, 메모리 저장소를 강제로 설정한다. 소켓 연결·DNS 시도를 가드로
막고 시도 횟수가 0인지 마지막 행에 표시한다.
"""

import base64
import json
import os
import socket
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from unittest import mock

DEMO_DATE = "2026-11-28"
DEMO_NOW = "2026-11-28T09:00:00+09:00"
DELAY_NOW = "2026-11-28T13:40:00+09:00"
FESTIVAL = "해운대 빛축제"
RETURN_DEPARTURE = "22:40"  # 장면 7: 막차 전 출발
RETURN_LAST_TRAINS = {"baseline": "23:29", "Dongbaek": "23:31", "Jung-dong": "23:28"}  # 서면 방향 토요일 막차


class NetworkBlocked(RuntimeError):
    """오프라인 점검 중 네트워크 연결을 시도했다."""


class NetworkGuard:
    """DNS와 소켓 연결 함수를 막고 시도 횟수를 센다."""

    def __init__(self):
        self.attempts = 0
        self._stack = ExitStack()

    def _blocked(self, *args, **kwargs):
        self.attempts += 1
        raise NetworkBlocked("오프라인 점검에서 네트워크 연결을 시도했습니다.")

    def __enter__(self):
        self._stack.enter_context(mock.patch.object(socket, "getaddrinfo", self._blocked))
        self._stack.enter_context(mock.patch.object(socket, "create_connection", self._blocked))
        self._stack.enter_context(mock.patch.object(socket.socket, "connect", self._blocked))
        self._stack.enter_context(mock.patch.object(socket.socket, "connect_ex", self._blocked))
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._stack.__exit__(exc_type, exc, traceback)


@dataclass
class Result:
    scene: str
    check: str
    ok: bool
    detail: str


def _record(rows: list[Result], scene: str, name: str, run, validate, detail) -> None:
    try:
        value = run()
        validate(value)
        rows.append(Result(scene, name, True, detail(value)))
    except Exception as error:
        rows.append(Result(scene, name, False, f"{type(error).__name__}: {error}"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_return_options(value: dict) -> None:
    """장면 7(22:40 출발) 결과의 막차 시각·경고·ranked·time_source 를 확인한다. 하나라도 다르면 AssertionError."""
    _require("error" not in value and bool(value.get("options")), "귀가 선택지가 없습니다.")
    options = {(o["type"], o["station"]): o for o in value["options"]}
    got = {
        "baseline": value["baseline"].get("last_train"),
        "Dongbaek": options.get(("walk_to_station", "Dongbaek"), {}).get("last_train"),
        "Jung-dong": options.get(("walk_to_station", "Jung-dong"), {}).get("last_train"),
    }
    _require(got == RETURN_LAST_TRAINS, f"막차 시각이 다릅니다: {got}")
    later = options.get(("shift_later", "Haeundae"))
    _require(later is not None and "last_train_missed" in later["warnings"], "shift_later 에 last_train_missed 가 없습니다.")
    ranked = value.get("ranked") or []
    _require(all(row["option"]["type"] != "shift_later" for row in ranked), "막차를 놓치는 shift_later 가 ranked 에 있습니다.")
    _require(bool(ranked) and "best" in ranked[0]["labels"], "ranked 첫 항목에 best 가 없습니다.")
    sources = {row.get("time_source") for row in (value["baseline"], *value["options"], *(r["option"] for r in ranked))}
    _require(sources == {"estimate"}, f"time_source 가 estimate 가 아닙니다: {sorted(map(str, sources))}")


def _handler_call(handler, make_event, method: str, path: str, body: dict | None = None,
                  query: dict[str, str] | None = None) -> dict:
    raw = None if body is None else json.dumps(body, ensure_ascii=False)
    response = handler(make_event(method, path, raw, query))
    parsed = json.loads(response["body"])
    _require(response["statusCode"] == 200, f"HTTP {response['statusCode']}: {parsed}")
    return parsed


def run_checks() -> tuple[list[Result], int]:
    """설정을 고정하고 모든 점검을 실행해 (표 행, 네트워크 시도 수)를 돌려준다."""
    os.environ["USE_MOCK"] = "1"
    os.environ["FAKE_LLM"] = "1"
    os.environ["STORAGE_BACKEND"] = "memory"

    # 환경 변수가 설정된 뒤 불러와 클라이언트 초기화 단계부터 오프라인 모드로 둔다.
    from app import config, storage
    from app.chat import demo_cache
    from app.handler import handler
    from app.models.plan import Profile
    from app.tools import lookup, return_options
    from scripts.local_invoke import make_event

    config.USE_MOCK = True
    config.FAKE_LLM = True
    config.STORAGE_BACKEND = "memory"
    storage.reset_mock_store(seed=False)
    profile = Profile(language="ja", interests=["sea"], companions="couple", diet=[], budget="mid")
    plan = demo_cache.build_plan("plan-offline-demo", profile)
    storage.create_plan(plan)

    rows: list[Result] = []
    with NetworkGuard() as guard:
        _record(
            rows, "1", "get_crowd", lambda: lookup.get_crowd("haeundae-beach", DEMO_DATE),
            lambda value: _require("error" not in value and value["ratio"] is not None, "집중률이 없습니다."),
            lambda value: f"ratio={value['ratio']}",
        )
        _record(
            rows, "1", "get_events", lambda: lookup.get_events(DEMO_DATE),
            lambda value: _require([e["name"] for e in value.get("events", [])] == [FESTIVAL], "Guardian 행사 규칙 결과가 다릅니다."),
            lambda value: f"{len(value['events'])}건(개막일 규칙)",
        )
        _record(
            rows, "2", "get_place_info", lambda: lookup.get_place_info("gwangalli-beach"),
            lambda value: _require(value.get("place_id") == "gwangalli-beach", "광안리 대체 장소를 읽지 못했습니다."),
            lambda value: value["place_id"],
        )
        _record(
            rows, "2", "get_travel_time", lambda: lookup.get_travel_time("haeundae-beach", "gwangalli-beach"),
            lambda value: _require(isinstance(value.get("minutes"), int), "이동 시간이 없습니다."),
            lambda value: f"약 {value['minutes']}분",
        )
        _record(
            rows, "5", "get_weather", lambda: lookup.get_weather(DEMO_DATE),
            lambda value: _require("error" not in value and isinstance(value.get("hourly"), list), "샘플 날씨를 읽지 못했습니다."),
            lambda value: f"{len(value['hourly'])}시간",
        )
        _record(
            rows, "7", "get_return_options",
            lambda: return_options.get_return_options(
                date=DEMO_DATE, event_name=FESTIVAL, planned_departure=RETURN_DEPARTURE
            ),
            check_return_options,
            lambda value: f"막차 {value['baseline']['last_train']}·ranked {len(value['ranked'])}개",
        )

        check_body = {
            "plan_id": plan.plan_id,
            "demo": {"now": DEMO_NOW, "weather_preset": "rain-afternoon"},
        }
        _record(
            rows, "1·2·5", "POST /plan/check",
            lambda: _handler_call(handler, make_event, "POST", "/plan/check", check_body),
            lambda value: _require(
                {"s3-crowded", "s3-rain"} <= {issue["issue_id"] for issue in value["issues"]}
                and bool(value["repairs"].get("s3-crowded")),
                "혼잡·비 점검 또는 대안이 없습니다.",
            ),
            lambda value: f"issues={len(value['issues'])}",
        )
        _record(
            rows, "5", "POST /plan/{id}/delay",
            lambda: _handler_call(
                handler, make_event, "POST", f"/plan/{plan.plan_id}/delay",
                {"plan_id": plan.plan_id, "delay_min": 30, "demo": {"now": DELAY_NOW}},
            ),
            lambda value: _require(isinstance(value.get("repairs"), list), "지연 응답 형식이 다릅니다."),
            lambda value: f"repairs={len(value['repairs'])}",
        )
        _record(
            rows, "현지인 카드", "POST /speak",
            lambda: _handler_call(
                handler, make_event, "POST", "/speak", {"text": "서면역은 어디예요?", "language": "ko"}
            ),
            lambda value: _require(
                value.get("content_type") == "audio/mpeg" and bool(base64.b64decode(value["audio_base64"], validate=True)),
                "mock MP3가 없습니다.",
            ),
            lambda value: f"audio={len(base64.b64decode(value['audio_base64']))}B",
        )
        _record(
            rows, "지도", "GET /events",
            lambda: _handler_call(handler, make_event, "GET", "/events", query={"date": DEMO_DATE}),
            lambda value: _require(len(value.get("events", [])) == 4, "11/28 지도 행사가 4건이 아닙니다."),
            lambda value: f"events={len(value['events'])}",
        )

    rows.append(Result("공통", "USE_MOCK / FAKE_LLM", config.USE_MOCK and config.FAKE_LLM, "1 / 1"))
    rows.append(Result("공통", "네트워크 소켓 시도", guard.attempts == 0, str(guard.attempts)))
    return rows, guard.attempts


def print_table(rows: list[Result]) -> None:
    headers = ("장면", "점검", "결과", "상세")
    values = [(row.scene, row.check, "성공" if row.ok else "실패", row.detail) for row in rows]
    widths = [max(len(headers[i]), *(len(row[i]) for row in values)) for i in range(4)]

    def line(parts):
        return "| " + " | ".join(part.ljust(widths[i]) for i, part in enumerate(parts)) + " |"

    print(line(headers))
    print("|-" + "-|-".join("-" * width for width in widths) + "-|")
    for value in values:
        print(line(value))


def main() -> int:
    rows, attempts = run_checks()
    print_table(rows)
    passed = sum(row.ok for row in rows)
    print(f"\n합계 {passed}/{len(rows)} 성공, 네트워크 호출 {attempts}회")
    return 0 if passed == len(rows) and attempts == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
