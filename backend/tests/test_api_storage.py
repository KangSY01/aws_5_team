"""GET·PUT /plan 과 Guardian 경로가 app/storage 의 일정을 쓰는지 확인한다.

저장소는 conftest.py 의 api_storage(샘플 일정 plan-1 이 든 메모리 저장소)를 쓰고, 테스트마다 새로 만들어진다.
Guardian 의 탐지·해결 로직은 D 의 코드를 그대로 쓰고, 조회 도구만 가짜로 바꿔 넣는다.
"""

import datetime as dt
import json
from types import SimpleNamespace

import pytest

import app.handler as handler_module
from app import storage
from app.guardian.repair import apply_option
from app.guardian.service import run_check, run_delay
from app.handler import SAMPLE_PLAN, handler
from app.models.api import CheckResponse, DelayResponse, DemoOverride, PlanResponse
from app.models.plan import Plan, Stop
from app.storage import InvalidDataError, PlanAccessDeniedError, PlanNotFoundError, StorageError
from scripts.local_invoke import make_event

PLAN_ID = SAMPLE_PLAN.plan_id
KST = dt.timezone(dt.timedelta(hours=9))
# 샘플: s1 감천 10:00-11:30 · s2 자갈치(고정) 12:00-13:00 · s3 부산타워 13:30-14:30 · s4 해운대 15:30-17:00


def at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, 21, hour, minute, tzinfo=KST)


def call(method: str, path: str, body: str | None = None) -> tuple[int, dict]:
    result = handler(make_event(method, path, body))
    return result["statusCode"], json.loads(result["body"])


def put(plan: Plan, plan_id: str | None = None) -> tuple[int, dict]:
    return call("PUT", f"/plan/{plan_id or plan.plan_id}", plan.model_dump_json())


def edit(plan: Plan, stop_id: str, **update) -> Plan:
    stops = [s.model_copy(update=update) if s.stop_id == stop_id else s for s in plan.stops]
    return plan.model_copy(update={"stops": stops})


def error_of(body: dict) -> tuple[str, str]:
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    return body["error"]["code"], body["error"]["message"]


# ---- GET /plan/{plan_id} ----


def test_get_returns_the_stored_plan_with_its_places(api_storage):
    other = SAMPLE_PLAN.model_copy(update={"plan_id": "plan-9", "stops": SAMPLE_PLAN.stops[2:]})
    api_storage.create_plan(other)

    status, body = call("GET", "/plan/plan-9")

    assert status == 200
    response = PlanResponse.model_validate(body)
    assert response.plan == other  # 샘플이 아니라 저장된 일정
    assert {p.place_id for p in response.places} == {"busan-tower", "haeundae-beach"}


def test_get_missing_plan_is_404():
    status, body = call("GET", "/plan/plan-none")
    assert status == 404
    assert error_of(body)[0] == "plan_not_found"


# ---- PUT /plan/{plan_id} ----


def test_put_then_get_shows_the_change(api_storage):
    modified = edit(edit(SAMPLE_PLAN, "s4", place_id="gwangalli-beach"), "s1", start=at(9), end=at(10, 30))

    status, body = put(modified)

    assert status == 200
    saved = PlanResponse.model_validate(body)
    assert saved.plan == modified
    place_ids = {p.place_id for p in saved.places}
    assert "gwangalli-beach" in place_ids and "haeundae-beach" not in place_ids
    assert PlanResponse.model_validate(call("GET", f"/plan/{PLAN_ID}")[1]).plan == modified
    assert api_storage.get_plan(PLAN_ID) == modified


def test_put_missing_plan_is_404_and_creates_nothing():
    missing = SAMPLE_PLAN.model_copy(update={"plan_id": "plan-none"})

    status, body = put(missing)

    assert status == 404 and error_of(body)[0] == "plan_not_found"
    assert call("GET", "/plan/plan-none")[0] == 404


def test_put_cannot_overwrite_another_plan(api_storage):
    api_storage.create_plan(SAMPLE_PLAN.model_copy(update={"plan_id": "plan-2"}))
    mismatch = SAMPLE_PLAN.model_copy(update={"plan_id": "plan-2"})

    status, body = put(edit(mismatch, "s4", place_id="gwangalli-beach"), plan_id=PLAN_ID)  # 경로 plan-1, 본문 plan-2

    assert status == 422 and error_of(body)[0] == "validation_error"
    assert api_storage.get_plan("plan-2").stops[3].place_id == "haeundae-beach"
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN

    changed = edit(mismatch, "s4", place_id="gwangalli-beach")
    assert put(changed)[0] == 200  # 자기 plan_id 로는 자기 일정만 바뀐다
    assert api_storage.get_plan("plan-2") == changed
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN


@pytest.mark.parametrize("place_id", ["no-such-place", "HAEUNDAE-BEACH"])
def test_put_rejects_place_not_in_places_json(api_storage, place_id):
    status, body = put(edit(SAMPLE_PLAN, "s4", place_id=place_id))
    code, message = error_of(body)
    assert status == 422 and code == "validation_error" and place_id in message
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN


LOCKED_CHANGES = {
    "장소 변경": edit(SAMPLE_PLAN, "s2", place_id="gwangalli-beach"),
    "시작 시각 변경": edit(SAMPLE_PLAN, "s2", start=at(12, 10)),
    "종료 시각 변경": edit(SAMPLE_PLAN, "s2", end=at(13, 10)),
    "제거": SAMPLE_PLAN.model_copy(update={"stops": [s for s in SAMPLE_PLAN.stops if s.stop_id != "s2"]}),
    "고정을 풀면서 변경": edit(SAMPLE_PLAN, "s2", locked=False, place_id="gwangalli-beach"),
}


@pytest.mark.parametrize("plan", LOCKED_CHANGES.values(), ids=LOCKED_CHANGES.keys())
def test_put_rejects_changes_to_locked_stop(api_storage, plan):
    status, body = put(plan)
    code, message = error_of(body)
    assert status == 422 and code == "validation_error"
    assert "s2" in message and "고정" in message
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN


def test_locked_flag_can_be_toggled_and_then_the_stop_can_be_edited(api_storage):
    assert put(edit(SAMPLE_PLAN, "s2", locked=False))[0] == 200  # 먼저 고정을 푼다
    unlocked = api_storage.get_plan(PLAN_ID)
    assert unlocked.stops[1].locked is False

    moved = edit(unlocked, "s2", place_id="gwangalli-beach")
    assert put(moved)[0] == 200 and api_storage.get_plan(PLAN_ID) == moved

    relocked = edit(moved, "s1", locked=True)  # 새로 고정하는 것도 된다
    assert put(relocked)[0] == 200
    assert put(edit(relocked, "s1", start=at(9), end=at(10, 30)))[0] == 422  # 이제 s1 은 고정


TIME_ERRORS = {
    "다른 Stop 과 일부 겹침": edit(SAMPLE_PLAN, "s3", start=at(12, 30)),
    "다른 Stop 안에 들어감": edit(SAMPLE_PLAN, "s1", start=at(12, 10), end=at(12, 50)),
    "같은 시각에 시작": SAMPLE_PLAN.model_copy(
        update={"stops": [*SAMPLE_PLAN.stops, Stop(stop_id="s5", place_id="busan-tower", start=at(10), end=at(11))]}
    ),
    "start 가 end 보다 늦음": edit(SAMPLE_PLAN, "s3", start=at(15), end=at(14)),
    "start 와 end 가 같음": edit(SAMPLE_PLAN, "s3", start=at(14), end=at(14)),
    "stop_id 중복": SAMPLE_PLAN.model_copy(
        update={"stops": [*SAMPLE_PLAN.stops, Stop(stop_id="s1", place_id="busan-tower", start=at(18), end=at(19))]}
    ),
}


@pytest.mark.parametrize("plan", TIME_ERRORS.values(), ids=TIME_ERRORS.keys())
def test_put_rejects_bad_times_and_duplicate_ids(api_storage, plan):
    status, body = put(plan)
    assert status == 422 and error_of(body)[0] == "validation_error"
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN


def test_put_allows_stops_that_touch_and_new_stops(api_storage):
    touching = edit(SAMPLE_PLAN, "s1", end=at(12))  # s1 이 끝나는 시각에 s2 가 시작
    added = touching.model_copy(
        update={"stops": [*touching.stops, Stop(stop_id="s5", place_id="busan-tower", start=at(18), end=at(19))]}
    )
    assert put(added)[0] == 200
    assert api_storage.get_plan(PLAN_ID) == added


# ---- Guardian 경로가 저장된 일정을 쓴다 ----


def test_check_uses_the_stored_plan(monkeypatch, api_storage):
    stored = SAMPLE_PLAN.model_copy(update={"plan_id": "plan-g", "stops": SAMPLE_PLAN.stops[1:]})
    api_storage.create_plan(stored)
    seen = []

    def spy(plan, demo=None, lookups=None):
        seen.append((plan, demo))
        return CheckResponse(plan_id=plan.plan_id, checked_at=at(9), issues=[], repairs={}, places=[])

    monkeypatch.setattr(handler_module.guardian, "run_check", spy)

    status, body = call("POST", "/plan/check", json.dumps({"plan_id": "plan-g", "demo": {"now": at(9).isoformat()}}))

    assert status == 200 and CheckResponse.model_validate(body).plan_id == "plan-g"
    (plan, demo), = seen
    assert plan == stored  # 샘플이 아니라 저장된 일정을 점검한다
    assert demo.now == at(9)


def test_delay_uses_the_stored_plan(monkeypatch, api_storage):
    stored = SAMPLE_PLAN.model_copy(update={"plan_id": "plan-g", "stops": SAMPLE_PLAN.stops[1:]})
    api_storage.create_plan(stored)
    seen = []

    def spy(plan, delay_min, demo=None, lookups=None):
        seen.append((plan, delay_min))
        return DelayResponse(plan_id=plan.plan_id, now=at(13, 40), repairs=[], places=[])

    monkeypatch.setattr(handler_module.guardian, "run_delay", spy)

    status, body = call("POST", "/plan/plan-g/delay", json.dumps({"plan_id": "plan-g", "delay_min": 30}))

    assert status == 200 and DelayResponse.model_validate(body).plan_id == "plan-g"
    assert seen == [(stored, 30)]


def test_guardian_is_not_called_for_missing_plans(monkeypatch):
    called = []
    monkeypatch.setattr(handler_module.guardian, "run_check", lambda *a, **k: called.append("check"))
    monkeypatch.setattr(handler_module.guardian, "run_delay", lambda *a, **k: called.append("delay"))

    assert call("POST", "/plan/check", json.dumps({"plan_id": "plan-none"}))[0] == 404
    assert call("POST", "/plan/plan-none/delay", json.dumps({"plan_id": "plan-none", "delay_min": 30}))[0] == 404
    assert called == []


# ---- Guardian 조회 도구를 가짜로 바꿔 실제 해결안을 만든다 ----


def rain(start_hour: int, end_hour: int) -> dict:
    return {
        "date": "2026-11-21",
        "hourly": [
            {"time": at(h).isoformat(), "pop": 80 if start_hour <= h < end_hour else 10, "pty": 1 if start_hour <= h < end_hour else 0}
            for h in range(8, 21)
        ],
    }


def fake_lookups(weather: dict) -> SimpleNamespace:
    """design.md 「조회 도구 반환 형식」과 같은 dict 를 돌려주는 가짜 조회 도구. 이동 시간은 어디든 15분."""
    return SimpleNamespace(
        get_weather=lambda date: weather,
        get_crowd=lambda place_id, date: {"place_id": place_id, "date": date, "ratio": None, "source": "weekday_rule"},
        get_hours=lambda place_id: {"error": {"code": "not_found", "message": "영업 정보 없음"}},
        get_travel_time=lambda a, b: {"from_place_id": a, "to_place_id": b, "minutes": 15, "mode": "subway"},
        get_events=lambda date: {"date": date, "events": []},
    )


def guardian_options() -> list[tuple[str, object]]:
    """비 오는 날 점검 2가지와 지연 재조정 2가지에서 Guardian 이 내놓는 해결안 전부."""
    options = []
    for name, weather in (("rain-15-18", rain(15, 18)), ("rain-10-12", rain(10, 12))):
        response = run_check(SAMPLE_PLAN, DemoOverride(now=at(9)), lookups=fake_lookups(weather))
        options += [(f"{name}/{issue_id}", option) for issue_id, found in response.repairs.items() for option in found]
    for delay_min in (30, 90):
        response = run_delay(SAMPLE_PLAN, delay_min, DemoOverride(now=at(13, 40)), lookups=fake_lookups(rain(0, 0)))
        options += [(f"delay-{delay_min}", option) for option in response.repairs]
    return options


GUARDIAN_OPTIONS = guardian_options()


def test_guardian_options_cover_all_repair_actions():
    assert {option.action for _, option in GUARDIAN_OPTIONS} == {"move_time", "reorder", "replace", "remove"}


@pytest.mark.parametrize(
    "option",
    [option for _, option in GUARDIAN_OPTIONS],
    ids=[f"{name}:{option.action}:{i}" for i, (name, option) in enumerate(GUARDIAN_OPTIONS)],
)
def test_guardian_repair_can_be_saved_with_put(api_storage, option):
    applied = apply_option(SAMPLE_PLAN, option)

    status, body = put(applied)

    assert status == 200, body
    assert PlanResponse.model_validate(body).plan == applied
    assert api_storage.get_plan(PLAN_ID) == applied
    kept = next(s for s in api_storage.get_plan(PLAN_ID).stops if s.stop_id == "s2")
    assert kept == SAMPLE_PLAN.stops[1]  # 고정된 자갈치시장은 그대로 (remove 로 순서가 바뀌어도 stop_id 로 찾는다)


def test_guardian_results_are_not_saved_automatically(monkeypatch, api_storage):
    def with_fakes(original, weather):
        return lambda plan, *args, **kwargs: original(plan, *args, lookups=fake_lookups(weather), **kwargs)

    monkeypatch.setattr(handler_module.guardian, "run_check", with_fakes(run_check, rain(15, 18)))
    monkeypatch.setattr(handler_module.guardian, "run_delay", with_fakes(run_delay, rain(0, 0)))
    monkeypatch.setattr(api_storage, "update_plan", lambda plan: pytest.fail("Guardian 결과를 저장하면 안 된다"))

    status, body = call("POST", "/plan/check", json.dumps({"plan_id": PLAN_ID, "demo": {"now": at(9).isoformat()}}))
    assert status == 200
    checked = CheckResponse.model_validate(body)
    assert checked.issues and any(options for options in checked.repairs.values())  # 해결안은 돌려준다

    status, body = call(
        "POST", f"/plan/{PLAN_ID}/delay",
        json.dumps({"plan_id": PLAN_ID, "delay_min": 30, "demo": {"now": at(13, 40).isoformat()}}),
    )
    assert status == 200 and DelayResponse.model_validate(body).repairs

    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN  # 저장된 일정은 그대로
    assert PlanResponse.model_validate(call("GET", f"/plan/{PLAN_ID}")[1]).plan == SAMPLE_PLAN


# ---- 저장소 오류 변환 ----


@pytest.mark.parametrize(
    "error, status, code",
    [
        (PlanNotFoundError("plan-x"), 404, "plan_not_found"),
        (PlanAccessDeniedError("plan-x"), 404, "plan_not_found"),
        (InvalidDataError("plan_id 는 비어 있지 않은 문자열이어야 합니다."), 422, "validation_error"),
        (StorageError("ResourceNotFoundException arn:aws:dynamodb:ap-northeast-2:060151520349:table/secret-table"), 500, "internal_error"),
    ],
)
@pytest.mark.parametrize("path, method, body", [("/plan/plan-x", "GET", None), ("/plan/check", "POST", '{"plan_id": "plan-x"}')])
def test_storage_errors_become_contract_errors(monkeypatch, error, status, code, path, method, body):
    def raise_error(plan_id):
        raise error

    monkeypatch.setattr(storage, "get_plan", raise_error)

    got_status, got_body = call(method, path, body)

    assert got_status == status and error_of(got_body)[0] == code
    assert "arn:aws" not in json.dumps(got_body) and "secret-table" not in json.dumps(got_body)  # 내부 정보는 노출하지 않는다


def test_access_denied_looks_the_same_as_not_found(monkeypatch):
    def deny(plan_id):
        raise PlanAccessDeniedError(plan_id)

    status, denied = call("GET", "/plan/plan-none")
    monkeypatch.setattr(storage, "get_plan", deny)
    denied_status, denied_body = call("GET", "/plan/plan-none")
    assert (denied_status, denied_body) == (status, denied)


def test_put_storage_failure_is_500_without_details(monkeypatch, api_storage):
    def fail(plan):
        raise StorageError("AccessDeniedException: user/secret-user")

    monkeypatch.setattr(api_storage, "update_plan", fail)

    status, body = put(edit(SAMPLE_PLAN, "s4", place_id="gwangalli-beach"))

    assert status == 500 and error_of(body) == ("internal_error", "서버 오류가 발생했습니다.")
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN


# ---- 테스트 간 격리 ----


def test_state_isolation_part_1_changes_the_stored_plan(api_storage):
    assert put(edit(SAMPLE_PLAN, "s4", place_id="gwangalli-beach"))[0] == 200


def test_state_isolation_part_2_starts_from_the_sample(api_storage):
    assert api_storage.get_plan(PLAN_ID) == SAMPLE_PLAN
